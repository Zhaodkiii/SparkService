import uuid
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIRequestFactory,force_authenticate
from .models import *
from .services import prepare,process,quote,wallet
from .identity import BillingError
from .provider import ProviderResult
from .views import Webhook,Wallet

@override_settings(DIAMOND_REDEMPTION_ENABLED=True,REVENUECAT_PROJECT_ID='test-project',REVENUECAT_APP_ID='test-app',REVENUECAT_CONFIRMED_REPLAY_SECONDS=3600)
class BillingConsistencyTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('billing-user')
        self.identity=BillingIdentity.objects.create(account=self.user,rc_project_id='test-project',wallet_domain='sandbox')
        WalletGate.objects.create(identity=self.identity)
        WalletSnapshot.objects.create(identity=self.identity)
        self.offer=ContentOffer.objects.create(target_kind='sticker_library',target_id=uuid.uuid4(),title='Test pack',state='active')
        self.policy=ContentPolicyRevision.objects.create(offer=self.offer,revision=1,access_mode='diamond_only',diamond_price=40,currency_code='DIAMOND')
        self.offer.current_policy_revision=self.policy;self.offer.save()
        self.q=RedemptionQuote.objects.create(identity=self.identity,offer=self.offer,policy_revision=self.policy,quoted_units=40,expires_at=timezone.now()+timedelta(minutes=10))
        self.target=patch('billing.services.target_available',return_value=True);self.target.start();self.addCleanup(self.target.stop)
    def order(self,key=None):
        return prepare(self.identity,self.q.pk,self.offer.pk,key or uuid.uuid4())
    def success(self): return ProviderResult(200,{'items':[{'currency_code':'DIAMOND','balance':60}]})
    @patch('billing.services.RevenueCat.transact')
    def test_once_only_and_no_webhook_needed(self,provider):
        provider.return_value=self.success();order=self.order();op=order.operations.get();process(op.pk);process(op.pk)
        order.refresh_from_db();self.assertEqual(order.status,'fulfilled');self.assertEqual(provider.call_count,1)
        self.assertEqual(ContentOwnership.objects.count(),1);self.assertEqual(WalletLedgerEntry.objects.count(),1)
    def test_different_device_keys_share_one_content_order(self):
        a=self.order();b=self.order();self.assertEqual(a.pk,b.pk);self.assertEqual(WalletOperation.objects.count(),1)
    def test_same_key_changed_quote_rejected(self):
        key=uuid.uuid4();self.order(key)
        with self.assertRaises(BillingError): prepare(self.identity,uuid.uuid4(),self.offer.pk,key)
    @patch('billing.services.RevenueCat.transact')
    def test_timeout_reuses_original_key(self,provider):
        provider.side_effect=[ProviderResult(0,{}),self.success()]
        order=self.order();op=order.operations.get();key=op.rc_idempotency_key
        process(op.pk);order.refresh_from_db();self.assertEqual(order.status,'debit_unknown');self.assertFalse(ContentOwnership.objects.exists())
        WalletOperation.objects.filter(pk=op.pk).update(next_attempt_at=timezone.now()-timedelta(seconds=1))
        process(op.pk);op.refresh_from_db();self.assertEqual(op.rc_idempotency_key,key);self.assertEqual(op.state,'succeeded')
        self.assertEqual(provider.call_count,2)
    @patch('billing.services.RevenueCat.transact')
    def test_unverified_replay_window_never_blindly_retries(self,provider):
        provider.return_value=ProviderResult(0,{})
        op=self.order().operations.get();process(op.pk)
        WalletOperation.objects.filter(pk=op.pk).update(next_attempt_at=None)
        with override_settings(REVENUECAT_CONFIRMED_REPLAY_SECONDS=0): process(op.pk)
        self.assertEqual(provider.call_count,1);self.assertEqual(ReconciliationCase.objects.count(),1)
    @patch('billing.services.RevenueCat.transact')
    def test_price_changes_before_send_do_not_debit(self,provider):
        op=self.order().operations.get();ContentOffer.objects.filter(pk=self.offer.pk).update(current_policy_revision=None)
        process(op.pk);self.assertFalse(provider.called);op.refresh_from_db();self.assertEqual(op.state,'rejected')
    @patch('billing.services.RevenueCat.transact')
    def test_provider_422_is_not_assumed_insufficient(self,provider):
        provider.return_value=ProviderResult(422,{'type':'unknown_error'})
        op=self.order().operations.get();process(op.pk);op.refresh_from_db();self.assertEqual(op.state,'manual_review');self.assertFalse(ContentOwnership.objects.exists())
    @patch('billing.services.RevenueCat.balance')
    def test_missing_currency_does_not_become_zero(self,provider):
        provider.return_value=ProviderResult(200,{'items':[]})
        result=wallet(self.identity,True);self.assertIsNone(result['balance']);self.assertEqual(result['balance_state'],'stale')
    def test_other_account_cannot_read_wallet(self):
        session=WalletSession.objects.create(identity=self.identity,expires_at=timezone.now()+timedelta(hours=1),proof_digest='x')
        request=APIRequestFactory().get('/wallet/',HTTP_X_BILLING_SESSION=str(session.pk))
        force_authenticate(request,user=User.objects.create_user('other'))
        self.assertEqual(Wallet.as_view()(request).status_code,403)
    def test_malformed_session_does_not_raise_500(self):
        request=APIRequestFactory().get('/wallet/',HTTP_X_BILLING_SESSION='invalid')
        force_authenticate(request,user=self.user)
        self.assertEqual(Wallet.as_view()(request).status_code,403)
    @override_settings(REVENUECAT_WEBHOOK_AUTH='Bearer fixture-only')
    def test_duplicate_currency_event_not_double_recorded(self):
        body={'event':{'id':'test-event','app_id':'test-app','app_user_id':str(self.identity.rc_app_user_id),'purchase_environment':'SANDBOX','type':'VIRTUAL_CURRENCY_TRANSACTION','virtual_currency_transaction_id':'vc-1','source':'admin_api','adjustments':[{'amount':60,'currency':{'code':'DIAMOND'}}]}}
        for _ in range(2):
            request=APIRequestFactory().post('/hook/',body,format='json',HTTP_AUTHORIZATION='Bearer fixture-only');self.assertEqual(Webhook.as_view()(request).status_code,200)
        self.assertEqual(WalletLedgerEntry.objects.count(),1)
        self.assertIsNone(WalletSnapshot.objects.get(identity=self.identity).provider_balance)

    @patch('billing.services.RevenueCat.transact')
    def test_refund_webhook_during_debit_preserves_review_gate(self,provider):
        def respond(operation):
            WalletGate.objects.filter(identity=self.identity).update(state='refund_review')
            return self.success()
        provider.side_effect=respond
        process(self.order().operations.get().pk)
        gate=WalletGate.objects.get(identity=self.identity)
        self.assertEqual(gate.state,'refund_review')
        self.assertIsNone(gate.active_operation_id)

    @patch('billing.services.RevenueCat.transact')
    def test_quarantine_during_timeout_is_not_cleared(self,provider):
        def respond(operation):
            WalletGate.objects.filter(identity=self.identity).update(state='quarantined')
            return ProviderResult(0,{})
        provider.side_effect=respond
        process(self.order().operations.get().pk)
        self.assertEqual(WalletGate.objects.get(identity=self.identity).state,'quarantined')

    @patch('billing.services.RevenueCat.transact')
    def test_compensation_is_unique_and_revokes_only_its_grants(self,provider):
        from .refunds import compensate
        provider.return_value=self.success()
        order=self.order();debit=order.operations.get();process(debit.pk)
        other=ContentOwnership.objects.create(identity=self.identity,target_kind='template',target_id=uuid.uuid4(),grant_line='legacy',source_kind='legacy')
        compensation=compensate(debit.pk,self.user,'未交付退款')
        self.assertEqual(compensate(debit.pk,self.user,'重复点击').pk,compensation.pk)
        process(compensation.pk)
        order.refresh_from_db();other.refresh_from_db()
        self.assertEqual(order.status,'compensated');self.assertEqual(other.state,'active')
        self.assertFalse(ContentOwnership.objects.filter(source_order=order,state='active').exists())
        self.assertEqual(provider.call_count,2)

    @override_settings(DIAMOND_CUSTOMIZATION_ENABLED=True)
    @patch('billing.customization.RevenueCat.transact')
    def test_custom_refund_does_not_revalidate_expired_member_price(self,provider):
        from diary_customizations.models import Request,Submission
        from .customization import issue_quote,prepare_funding
        from .refunds import compensate
        request=Request.objects.create(owner=self.user,creation_key=uuid.uuid4(),status='submitted',title='Test commission')
        Submission.objects.create(request=request,number=1,snapshot={})
        package=CustomizationPackage.objects.create(code='test',title='test',state='active')
        revision=CustomizationPackageRevision.objects.create(package=package,revision=1,standard_diamonds=80,pro_diamonds=60,terms_version='1')
        q=issue_quote(request.pk,revision.pk,self.user)
        MembershipSnapshot.objects.create(identity=self.identity,verified_at=timezone.now(),active_until=timezone.now()+timedelta(days=1))
        funding=prepare_funding(self.identity,request.pk,q.pk,q.revision,request.revision,uuid.uuid4(),60)
        provider.return_value=self.success()
        debit=funding.operations.get();process(debit.pk)
        MembershipSnapshot.objects.filter(identity=self.identity).update(active_until=timezone.now()-timedelta(days=1))
        refund=compensate(debit.pk,self.user,'未开工取消')
        process(refund.pk)
        funding.refresh_from_db();refund.refresh_from_db()
        self.assertEqual(funding.status,'refunded');self.assertEqual(refund.state,'succeeded')
        self.assertEqual(provider.call_count,2)

    @override_settings(BILLING_SANDBOX_SALES_ENABLED=True,DIAMOND_RECHARGE_ENABLED=False)
    def test_sandbox_override_cannot_open_production_sales(self):
        from .flags import enabled
        self.assertTrue(enabled('DIAMOND_RECHARGE_ENABLED',self.identity))
        production=BillingIdentity.objects.create(account=self.user,rc_project_id='test-project',wallet_domain='production')
        self.assertFalse(enabled('DIAMOND_RECHARGE_ENABLED',production))

    @override_settings(REVENUECAT_WEBHOOK_AUTH='Bearer fixture-only')
    def test_sandbox_callback_rejects_production_events(self):
        from .views import SandboxWebhook
        data={'event':{'id':'production-misroute','app_id':'test-app','environment':'PRODUCTION','type':'INITIAL_PURCHASE'}}
        request=APIRequestFactory().post('/hook/',data,format='json',HTTP_AUTHORIZATION='Bearer fixture-only')
        self.assertEqual(SandboxWebhook.as_view()(request).status_code,403)
        self.assertFalse(CurrencyEvent.objects.exists())

    @override_settings(REVENUECAT_WEBHOOK_AUTH='Bearer fixture-only')
    def test_malformed_currency_event_is_quarantined_without_ledger(self):
        body={'event':{'id':'malformed','app_id':'test-app','app_user_id':str(self.identity.rc_app_user_id),'environment':'SANDBOX','type':'VIRTUAL_CURRENCY_TRANSACTION','adjustments':[{'amount':'60','currency':{'code':'DIAMOND'}}]}}
        request=APIRequestFactory().post('/hook/',body,format='json',HTTP_AUTHORIZATION='Bearer fixture-only')
        self.assertEqual(Webhook.as_view()(request).status_code,200)
        self.assertEqual(CurrencyEvent.objects.get().state,'quarantined')
        self.assertFalse(WalletLedgerEntry.objects.exists())

    def test_topup_events_out_of_order_do_not_downgrade_confirmed_grant(self):
        from .topups import observe
        RechargeProduct.objects.create(rc_project_id='test-project',apple_product_id='diamonds.60',units=60,rc_product_id='rc60',rc_package_id='60')
        data={'transaction_id':'apple-123','store':'APP_STORE','product_id':'diamonds.60','type':'VIRTUAL_CURRENCY_TRANSACTION'}
        row=observe(self.identity,data,60)
        data['type']='NON_RENEWING_PURCHASE';same=observe(self.identity,data)
        self.assertEqual(row.pk,same.pk);self.assertEqual(same.state,'granted');self.assertEqual(TopUpRecord.objects.count(),1)

    def test_topup_units_mismatch_creates_reconciliation_case(self):
        from .topups import observe
        RechargeProduct.objects.create(rc_project_id='test-project',apple_product_id='diamonds.60',units=60,rc_product_id='rc60',rc_package_id='60')
        data={'transaction_id':'apple-mismatch','store':'APP_STORE','product_id':'diamonds.60'}
        self.assertIs(observe(self.identity,data,300),False)
        self.assertEqual(TopUpRecord.objects.get().state,'unknown')
        self.assertEqual(ReconciliationCase.objects.get().kind,'topup_units_mismatch')

    def test_one_store_transaction_cannot_belong_to_two_business_users(self):
        from .topups import observe
        RechargeProduct.objects.create(rc_project_id='test-project',apple_product_id='diamonds.60',units=60,rc_product_id='rc60',rc_package_id='60')
        data={'transaction_id':'apple-shared','store':'APP_STORE','product_id':'diamonds.60'}
        observe(self.identity,data,60)
        other=BillingIdentity.objects.create(account=User.objects.create_user('second-buyer'),rc_project_id='test-project',wallet_domain='sandbox')
        self.assertIs(observe(other,data,60),False)
        self.assertEqual(TopUpRecord.objects.count(),1)

    def test_publish_requires_same_draft_that_operator_reviewed(self):
        from .pricing import save_draft,publish
        from .services import digest
        body={'expected_revision':1,'access_mode':'diamond_only','diamond_price':40,'currency_code':'DIAMOND','pro_entitlement_key':None,'bundled_grants':[],'terms_version':'1','change_reason':'first price'}
        draft=save_draft(self.offer.pk,body,self.user);reviewed=digest(draft.body)
        save_draft(self.offer.pk,{**body,'diamond_price':60,'change_reason':'concurrent change'},self.user)
        with self.assertRaises(BillingError) as error: publish(self.offer.pk,self.user,reviewed)
        self.assertEqual(str(error.exception.detail['code']),'DRAFT_CHANGED')
        self.assertEqual(ContentPolicyRevision.objects.count(),1)

    @override_settings(DIAMOND_REDEMPTION_ENABLED=False)
    @patch('billing.pricing.target_available',return_value=True)
    def test_production_paid_policy_cannot_publish_when_sales_disabled(self,_available):
        from .pricing import save_draft,publish
        from .services import digest
        body={'expected_revision':1,'access_mode':'diamond_only','diamond_price':40,'currency_code':'DIAMOND','pro_entitlement_key':None,'bundled_grants':[],'terms_version':'1','change_reason':'release gate test'}
        draft=save_draft(self.offer.pk,body,self.user)
        with self.assertRaises(BillingError) as error: publish(self.offer.pk,self.user,digest(draft.body))
        self.assertEqual(str(error.exception.detail['code']),'SALES_DISABLED')


    def test_blank_change_reason_does_not_save_a_pricing_draft(self):
        from .pricing import save_draft
        from rest_framework.exceptions import ValidationError
        body={'expected_revision':1,'access_mode':'diamond_only','diamond_price':30,'currency_code':'DIAMOND','pro_entitlement_key':None,'bundled_grants':[],'terms_version':'1','change_reason':'  '}
        with self.assertRaises(ValidationError) as error: save_draft(self.offer.pk,body,self.user)
        self.assertIn('请填写变更说明',str(error.exception.detail['change_reason']))
        self.assertFalse(ContentPolicyDraft.objects.exists())

    def test_paid_draft_with_reason_does_not_change_the_online_policy(self):
        from .pricing import save_draft
        self.policy.access_mode='free';self.policy.diamond_price=None;self.policy.currency_code=None;self.policy.save()
        body={'expected_revision':1,'access_mode':'diamond_only','diamond_price':30,'currency_code':'DIAMOND','pro_entitlement_key':None,'bundled_grants':[],'terms_version':'1','change_reason':'首次设置数字内容售价'}
        saved=save_draft(self.offer.pk,body,self.user)
        self.offer.refresh_from_db()
        self.assertEqual(saved.body['diamond_price'],30)
        self.assertEqual(self.offer.current_policy_revision.access_mode,'free')
        self.assertEqual(ContentPolicyRevision.objects.count(),1)


    @override_settings(DIAMOND_REDEMPTION_ENABLED=True,BILLING_TEST_POLICY_CHANGES_ENABLED=True)
    @patch('billing.pricing.target_available',return_value=True)
    def test_local_test_configuration_allows_free_to_diamond_publication(self,_available):
        from .pricing import save_draft,publish
        from .services import digest
        self.policy.access_mode='free';self.policy.diamond_price=None;self.policy.currency_code=None;self.policy.save()
        body={'expected_revision':1,'access_mode':'diamond_only','diamond_price':30,'currency_code':'DIAMOND','pro_entitlement_key':None,'bundled_grants':[],'terms_version':'1','change_reason':'本地测试收费切换'}
        draft=save_draft(self.offer.pk,body,self.user)
        policy=publish(self.offer.pk,self.user,digest(draft.body))
        self.offer.refresh_from_db()
        self.assertEqual(policy.diamond_price,30)
        self.assertEqual(self.offer.current_policy_revision_id,policy.pk)

    @override_settings(DIAMOND_REDEMPTION_ENABLED=True,BILLING_TEST_POLICY_CHANGES_ENABLED=False)
    @patch('billing.pricing.target_available',return_value=True)
    def test_normal_configuration_preserves_existing_free_scope(self,_available):
        from .pricing import save_draft,publish
        from .services import digest
        self.policy.access_mode='free';self.policy.diamond_price=None;self.policy.currency_code=None;self.policy.save()
        body={'expected_revision':1,'access_mode':'diamond_only','diamond_price':30,'currency_code':'DIAMOND','pro_entitlement_key':None,'bundled_grants':[],'terms_version':'1','change_reason':'正常环境保护测试'}
        draft=save_draft(self.offer.pk,body,self.user)
        with self.assertRaises(BillingError) as error: publish(self.offer.pk,self.user,digest(draft.body))
        self.assertEqual(str(error.exception.detail['code']),'MIGRATION_REQUIRED')
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.current_policy_revision.access_mode,'free')

    @patch('billing.pricing.target_available',return_value=True)
    def test_published_draft_is_removed_and_repeat_publish_does_not_create_version(self,_available):
        from .pricing import save_draft,publish
        from .services import digest
        body={'expected_revision':1,'access_mode':'diamond_only','diamond_price':100,'currency_code':'DIAMOND','pro_entitlement_key':None,'bundled_grants':[],'terms_version':'1','change_reason':'改价测试'}
        draft=save_draft(self.offer.pk,body,self.user);key=digest(draft.body)
        result=publish(self.offer.pk,self.user,key)
        self.assertEqual(result.revision,2)
        self.assertFalse(ContentPolicyDraft.objects.filter(offer=self.offer).exists())
        with self.assertRaises(BillingError) as error: publish(self.offer.pk,self.user,key)
        self.assertEqual(str(error.exception.detail['code']),'DRAFT_NOT_FOUND')
        self.assertEqual(ContentPolicyRevision.objects.filter(offer=self.offer).count(),2)

    def test_edit_hides_stale_draft_and_returns_current_published_policy(self):
        from .manage import ManagePolicy
        from .pricing import save_draft
        self.user.is_staff=True;self.user.is_superuser=True;self.user.save()
        body={'expected_revision':1,'access_mode':'diamond_only','diamond_price':100,'currency_code':'DIAMOND','pro_entitlement_key':None,'bundled_grants':[],'terms_version':'1','change_reason':'旧草稿'}
        save_draft(self.offer.pk,body,self.user)
        newer=ContentPolicyRevision.objects.create(offer=self.offer,revision=2,access_mode='diamond_only',diamond_price=100,currency_code='DIAMOND')
        self.offer.current_policy_revision=newer;self.offer.save()
        request=APIRequestFactory().get('/draft/');force_authenticate(request,user=self.user)
        response=ManagePolicy.as_view()(request,pk=self.offer.pk,action='draft')
        self.assertTrue(response.data['stale_draft']);self.assertIsNone(response.data['draft'])
        self.assertEqual(response.data['offer']['revision'],2)
        self.assertEqual(response.data['offer']['diamond_price'],100)

    def test_paid_template_denies_manifest_and_whole_book_download_without_ownership(self):
        from diary_presets.models import Series,Template,Version
        from diary_presets.views import Detail
        series=Series.objects.create(slug='paid-authorization-test',title='收费校验')
        template=Template.objects.create(series=series,title='收费模板')
        version=Version.objects.create(template=template,number=1,snapshot={})
        template.current=version;template.save()
        offer=ContentOffer.objects.create(target_kind='template',target_id=template.pk,title=template.title,state='active')
        policy=ContentPolicyRevision.objects.create(offer=offer,revision=1,access_mode='diamond_only',diamond_price=100,currency_code='DIAMOND')
        offer.current_policy_revision=policy;offer.save()
        for method in ('get','post'):
            request=getattr(APIRequestFactory(),method)('/template/',{},format='json')
            force_authenticate(request,user=self.user)
            response=Detail.as_view()(request,pk=template.pk,number=1)
            self.assertEqual(response.status_code,403)
