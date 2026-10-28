from datetime import timedelta
from unittest.mock import patch
from django.test import TransactionTestCase, override_settings
from django.contrib.auth.models import User
from django.utils import timezone
from .models import BillingIdentity, MembershipSnapshot, CurrencyEvent
from .provider import ProviderResult
from .membership import refresh, status, is_active
from .tasks import process_event

@override_settings(REVENUECAT_MEMBER_ENTITLEMENT_ID='member-internal', REVENUECAT_PROJECT_ID='test', REVENUECAT_APP_ID='app')
class MembershipTests(TransactionTestCase):
    def setUp(self):
        self.identity=BillingIdentity.objects.create(account=User.objects.create_user('member'),rc_project_id='test',wallet_domain='sandbox')
        self.future=timezone.now()+timedelta(days=30)
    def customer(self, until=None):
        return ProviderResult(200, {'active_entitlements':{'items':[] if until is None else [{'entitlement_id':'member-internal','expires_at':int(until.timestamp()*1000)}]}})
    def subscriptions(self, renewal='will_renew', state='active', access=True, environment='sandbox'):
        return ProviderResult(200, {'items':[dict(environment=environment,entitlements={'items':[{'id':'member-internal'}]},gives_access=access,status=state,auto_renewal_status=renewal,product_id='prod-month',current_period_ends_at=int(self.future.timestamp()*1000))]})
    @patch('billing.membership.RevenueCat')
    def test_cancel_keeps_paid_access(self, rc):
        rc.return_value.customer.return_value=self.customer(self.future)
        rc.return_value.subscriptions.return_value=self.subscriptions('will_not_renew')
        result=status(self.identity, True)
        self.assertTrue(result['active']);self.assertEqual(result['auto_renewal_status'],'will_not_renew')
    @patch('billing.membership.RevenueCat')
    def test_refund_and_expiration_revoke(self, rc):
        MembershipSnapshot.objects.create(identity=self.identity,active_until=self.future,verified_at=timezone.now())
        rc.return_value.customer.return_value=self.customer()
        rc.return_value.subscriptions.return_value=self.subscriptions('will_not_renew','expired',False)
        self.assertFalse(status(self.identity, True)['active'])
    @patch('billing.membership.RevenueCat')
    def test_grace_period_beyond_paid_expiry(self, rc):
        rc.return_value.customer.return_value=self.customer(timezone.now()-timedelta(seconds=1))
        rc.return_value.subscriptions.return_value=self.subscriptions(state='in_grace_period')
        self.assertTrue(status(self.identity, True)['active'])
        row=MembershipSnapshot.objects.get(identity=self.identity)
        self.assertFalse(is_active(row,self.identity,timezone.now()+timedelta(minutes=6)))
    @patch('billing.membership.RevenueCat')
    def test_wrong_environment_never_grants_grace(self, rc):
        rc.return_value.customer.return_value=self.customer()
        rc.return_value.subscriptions.return_value=self.subscriptions(state='in_grace_period',environment='production')
        self.assertFalse(status(self.identity, True)['active'])
    @patch('billing.membership.RevenueCat')
    def test_provider_outage_preserves_bounded_access(self, rc):
        MembershipSnapshot.objects.create(identity=self.identity,active_until=self.future,verified_at=timezone.now())
        rc.return_value.customer.return_value=ProviderResult(503,{})
        data=status(self.identity,True)
        self.assertTrue(data['active']);self.assertEqual(data['sync_state'],'stale')
        MembershipSnapshot.objects.filter(identity=self.identity).update(verified_at=timezone.now()-timedelta(hours=2))
        self.assertFalse(status(self.identity,True)['active'])
    @patch('billing.membership.RevenueCat')
    def test_incomplete_entitlements_do_not_revoke(self, rc):
        MembershipSnapshot.objects.create(identity=self.identity,active_until=self.future,verified_at=timezone.now())
        rc.return_value.customer.return_value=ProviderResult(200,{'active_entitlements':{'items':[],'next_page':'next'}})
        self.assertFalse(refresh(self.identity,True));self.assertTrue(is_active(MembershipSnapshot.objects.get(identity=self.identity),self.identity))
    @patch('billing.membership.RevenueCat')
    def test_late_http_cannot_overwrite_webhook_invalidation(self, rc):
        row=MembershipSnapshot.objects.create(identity=self.identity,active_until=self.future)
        def customer(identity):
            MembershipSnapshot.objects.filter(pk=row.pk).update(last_event_at=timezone.now(),needs_sync=True)
            return self.customer()
        rc.return_value.customer.side_effect=customer
        rc.return_value.subscriptions.return_value=ProviderResult(200,{'items':[]})
        self.assertFalse(refresh(self.identity,True));row.refresh_from_db();self.assertEqual(row.active_until,self.future)
    def test_duplicate_and_old_events_never_grant_from_payload(self):
        row=MembershipSnapshot.objects.create(identity=self.identity,active_until=None)
        event=CurrencyEvent.objects.create(event_id='old-renewal',payload={'app_user_id':str(self.identity.rc_app_user_id),'environment':'SANDBOX','type':'RENEWAL','entitlement_ids':['member'],'expiration_at_ms':int(self.future.timestamp()*1000)})
        process_event(event.pk);process_event(event.pk)
        row.refresh_from_db();self.assertIsNone(row.active_until);self.assertTrue(row.needs_sync)
    @patch('billing.membership.RevenueCat')
    def test_grace_without_provider_access_is_denied(self, rc):
        rc.return_value.customer.return_value=self.customer(timezone.now()-timedelta(seconds=1))
        rc.return_value.subscriptions.return_value=self.subscriptions(state='in_grace_period',access=False)
        self.assertFalse(status(self.identity,True)['active'])
    def test_transfer_invalidates_both_without_merging_accounts(self):
        other=BillingIdentity.objects.create(account=User.objects.create_user('other'),rc_project_id='test',wallet_domain='sandbox')
        for i in (self.identity,other): MembershipSnapshot.objects.create(identity=i,active_until=self.future,verified_at=timezone.now())
        event=CurrencyEvent.objects.create(event_id='transfer',payload={'type':'TRANSFER','transferred_from':[str(self.identity.rc_app_user_id)],'transferred_to':[str(other.rc_app_user_id)]})
        process_event(event.pk)
        self.assertEqual(MembershipSnapshot.objects.filter(verified_at=None,needs_sync=True).count(),2)
        self.assertEqual(BillingIdentity.objects.count(),2)
    @patch('billing.membership.RevenueCat')
    def test_member_content_requires_verified_access(self, rc):
        from .models import ContentOffer,ContentPolicyRevision
        from .access import describe
        from rest_framework.test import APIRequestFactory
        import uuid
        offer=ContentOffer.objects.create(target_kind='sticker_library',target_id=uuid.uuid4(),title='Pro',state='active')
        policy=ContentPolicyRevision.objects.create(offer=offer,revision=1,access_mode='pro_only',pro_entitlement_key='member',terms_version='test',content_scope_snapshot={})
        offer.current_policy_revision=policy;offer.save()
        request=APIRequestFactory().get('/',HTTP_X_BILLING_SESSION='test');request.user=self.identity.account
        rc.return_value.customer.return_value=self.customer(self.future)
        rc.return_value.subscriptions.return_value=self.subscriptions()
        with patch('billing.access.identity_for',return_value=self.identity):
            self.assertTrue(describe(request,offer.target_kind,offer.target_id)['access']['can_use'])
            rc.return_value.customer.return_value=self.customer()
            rc.return_value.subscriptions.return_value=self.subscriptions(state='expired',access=False)
            refresh(self.identity,True)
            self.assertFalse(describe(request,offer.target_kind,offer.target_id)['access']['can_use'])
