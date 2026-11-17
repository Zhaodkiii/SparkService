from unittest.mock import patch, Mock
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.utils import timezone
from .models import BillingIdentity, CurrencyEvent, WebhookDelivery, MembershipSnapshot
from .routing import ingest, new_identity_id, development_id, deliver_pending

@override_settings(BILLING_DEPLOYMENT='production', REVENUECAT_PROJECT_ID='test', REVENUECAT_APP_ID='app', BILLING_RELAY_TOKEN='relay-secret', BILLING_DEV_RELAY_URL='https://dev.example/relay')
class RoutingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('routing')
        with override_settings(BILLING_DEPLOYMENT='development'):
            self.dev_id = new_identity_id()
        self.event = {'id':'evt', 'app_id':'app', 'app_user_id':str(self.dev_id), 'type':'RENEWAL', 'environment':'SANDBOX'}

    def test_new_dev_identity_remains_uuid(self):
        self.assertTrue(development_id(str(self.dev_id)))
        self.assertEqual(self.dev_id.version, 4)
        self.assertFalse(development_id(str(new_identity_id())))

    def test_dev_event_is_persisted_once_not_quarantined(self):
        ingest(self.event); ingest(self.event)
        self.assertEqual(WebhookDelivery.objects.count(), 1)
        self.assertEqual(CurrencyEvent.objects.get().state, 'forwarding')

    def test_online_sandbox_is_processed_locally(self):
        identity = BillingIdentity.objects.create(account=self.user, rc_project_id='test', wallet_domain='sandbox')
        self.event['app_user_id'] = str(identity.rc_app_user_id)
        ingest(self.event)
        self.assertEqual(CurrencyEvent.objects.get().state, 'processed')
        self.assertFalse(WebhookDelivery.objects.exists())
        self.assertTrue(MembershipSnapshot.objects.get().needs_sync)

    def test_unmarked_unknown_identity_is_not_forwarded(self):
        self.event['app_user_id'] = str(new_identity_id())
        ingest(self.event)
        self.assertFalse(WebhookDelivery.objects.exists())
        self.assertEqual(CurrencyEvent.objects.get().state, 'quarantined')

    @patch('billing.routing.httpx.post')
    def test_offline_then_recovery(self, post):
        import httpx
        ingest(self.event)
        post.side_effect = httpx.ConnectError('offline')
        deliver_pending()
        row = WebhookDelivery.objects.get()
        self.assertIsNone(row.delivered_at)
        self.assertEqual(row.attempts, 1)
        self.assertGreater(row.next_attempt_at, timezone.now())
        WebhookDelivery.objects.update(next_attempt_at=timezone.now())
        post.side_effect = None
        post.return_value = Mock(status_code=200, json=lambda: {'received':True})
        deliver_pending(); deliver_pending()
        self.assertIsNotNone(WebhookDelivery.objects.get().delivered_at)
        self.assertEqual(CurrencyEvent.objects.get().state, 'forwarded')
        self.assertEqual(post.call_count, 2)

    @override_settings(BILLING_DEPLOYMENT='development')
    def test_receiver_auth_unknown_and_idempotency(self):
        path='/api/v1/billing/relay-webhook/'
        self.assertEqual(self.client.post(path, {'event':self.event}, content_type='application/json').status_code,403)
        def send():
            return self.client.post(path, {'event':self.event}, content_type='application/json', HTTP_AUTHORIZATION='relay-secret')
        self.assertEqual(send().status_code,409)
        BillingIdentity.objects.create(account=self.user, rc_project_id='test', wallet_domain='sandbox',rc_app_user_id=self.dev_id)
        self.assertEqual(send().status_code,200)
        self.assertEqual(send().status_code,200)
        self.assertEqual(CurrencyEvent.objects.count(),1)
        self.assertFalse(WebhookDelivery.objects.exists())
        self.event['environment']='PRODUCTION'
        self.assertEqual(send().status_code,403)

    def test_transfer_reaches_both_backends(self):
        identity=BillingIdentity.objects.create(account=self.user, rc_project_id='test', wallet_domain='sandbox')
        self.event.update(type='TRANSFER', transferred_from=[str(identity.rc_app_user_id)], transferred_to=[str(self.dev_id)])
        ingest(self.event)
        self.assertEqual(CurrencyEvent.objects.get().state,'processed')
        self.assertEqual(WebhookDelivery.objects.count(),1)
        self.assertTrue(MembershipSnapshot.objects.get(identity=identity).needs_sync)

    @override_settings(BILLING_DEPLOYMENT='development')
    @patch('billing.identity.verify_environment', return_value='sandbox')
    def test_bootstrap_reuses_existing_identity(self, verify):
        from billing.identity import bootstrap
        identity=BillingIdentity.objects.create(account=self.user, rc_project_id='test', wallet_domain='sandbox')
        first=bootstrap(self.user,'proof')
        second=bootstrap(self.user,'proof')
        self.assertEqual(first.identity.rc_app_user_id,identity.rc_app_user_id)
        self.assertEqual(second.identity_id,identity.pk)

    @override_settings(BILLING_DEPLOYMENT='development')
    @patch('billing.identity.verify_environment', return_value='production')
    def test_development_bootstrap_rejects_real_store(self, verify):
        from billing.identity import bootstrap, BillingError
        with self.assertRaises(BillingError): bootstrap(self.user,'proof')
        self.assertFalse(BillingIdentity.objects.exists())


    @patch('billing.identity.verify_environment', return_value='sandbox')
    def test_guest_bootstrap_without_personal_identity(self, verify):
        from billing.identity import bootstrap
        self.assertFalse(self.user.social_identities.exists())
        first = bootstrap(self.user, 'proof')
        second = bootstrap(self.user, 'proof')
        self.assertEqual(first.identity.account_id, self.user.pk)
        self.assertEqual(first.identity_id, second.identity_id)
        self.assertEqual(first.identity.wallet_domain, 'sandbox')

    @patch('billing.identity.verify_environment')
    def test_inactive_guest_cannot_bootstrap(self, verify):
        from billing.identity import bootstrap, BillingError
        self.user.is_active = False
        with self.assertRaises(BillingError):
            bootstrap(self.user, 'proof')
        verify.assert_not_called()

    @patch('billing.identity.verify_environment', return_value='sandbox')
    def test_guest_session_cannot_be_used_by_another_account(self, verify):
        from billing.identity import bootstrap, identity_for, BillingError
        session = bootstrap(self.user, 'proof')
        other = User.objects.create_user('different-guest')
        request = Mock(user=other, headers={'X-Billing-Session': str(session.pk)})
        with self.assertRaises(BillingError):
            identity_for(request)

    @patch('billing.identity.verify_environment', return_value='sandbox')
    def test_guest_upgrade_keeps_billing_identity(self, verify):
        from billing.identity import bootstrap
        from accounts.models import SocialIdentity
        before = bootstrap(self.user, 'proof')
        SocialIdentity.objects.create(user=self.user, bundle_id='test',
                                      provider='phone', provider_uid='test-upgraded-identity')
        after = bootstrap(self.user, 'proof')
        self.assertEqual(before.identity_id, after.identity_id)
        self.assertEqual(before.identity.rc_app_user_id, after.identity.rc_app_user_id)

    @patch('billing.identity.verify_environment')
    def test_bootstrap_still_requires_authenticated_device_session(self, verify):
        response = self.client.post('/api/v1/billing/bootstrap/',
                                    {'signed_app_transaction': 'proof'},
                                    content_type='application/json')
        self.assertIn(response.status_code, (401, 403))
        verify.assert_not_called()
