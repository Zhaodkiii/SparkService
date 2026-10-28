import uuid
from django.test import TestCase,override_settings
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory,force_authenticate
from .models import BillingIdentity,CurrencyEvent,StorePayment
from .reporting import project
from .transactions import Transactions,PaymentDetail,UserAssets

@override_settings(REVENUECAT_PROJECT_ID='project',REVENUECAT_APP_ID='app')
class ReportingTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('buyer')
        self.admin=User.objects.create_superuser('operator','test@example.com','test')
        self.identity=BillingIdentity.objects.create(account=self.user,rc_project_id='project',wallet_domain='sandbox')
    def event(self,kind='INITIAL_PURCHASE',at=1700000000000,**extra):
        data=dict(type=kind,app_id='app',store='APP_STORE',transaction_id='tx-1',product_id='member.month',environment='SANDBOX',event_timestamp_ms=at,purchased_at_ms=1699999999000,currency='CNY',price_in_purchased_currency=18)
        data.update(extra)
        e=CurrencyEvent.objects.create(event_id=str(uuid.uuid4()),identity=self.identity,state='processed',payload=data);project(e);return e
    def request(self,view,query=None,user=None,**kwargs):
        r=APIRequestFactory().get('/',query or {});force_authenticate(r,user=user or self.admin)
        return view.as_view()(r,**kwargs)
    def test_duplicates_and_unknown_amount(self):
        e=self.event(price_in_purchased_currency=None);project(e)
        self.assertEqual(StorePayment.objects.count(),1);self.assertIsNone(StorePayment.objects.get().amount)
        self.event();row=StorePayment.objects.get();self.assertEqual(row.amount,18);self.assertEqual(row.events.count(),2)
    def test_cancel_autorenew_is_not_refund(self):
        self.event();self.event('CANCELLATION',at=1700000001000,cancel_reason='UNSUBSCRIBE')
        r=StorePayment.objects.get();self.assertEqual(r.refund_state,'none');self.assertTrue(r.payment_confirmed)
    def test_refund_survives_out_of_order_purchase_and_reversal(self):
        self.event('CANCELLATION',at=1700000002000,cancel_reason='CUSTOMER_SUPPORT',price_in_purchased_currency=-18)
        self.event();r=StorePayment.objects.get();self.assertEqual(r.refund_state,'refunded');self.assertEqual(r.amount,18)
        self.event('REFUND_REVERSED',at=1700000003000);r.refresh_from_db();self.assertEqual(r.refund_state,'reversed')
        self.event('CANCELLATION',at=1700000001000,cancel_reason='CUSTOMER_SUPPORT');r.refresh_from_db();self.assertEqual(r.refund_state,'reversed')
    def test_environment_and_access_and_validation(self):
        self.event()
        self.assertEqual(self.request(Transactions).data['total'],0)
        response=self.request(Transactions,{'environment':'sandbox','section':'subscription'})
        self.assertEqual(response.data['total'],1);self.assertEqual(response.data['summary']['amounts'][0]['amount'],18)
        self.assertEqual(self.request(Transactions,{'page':'-1'}).status_code,400)
        self.assertEqual(self.request(Transactions,user=self.user).status_code,403)
        self.assertEqual(self.request(PaymentDetail,user=self.user,pk=StorePayment.objects.get().pk).status_code,403)
    def test_pending_or_wrong_environment_never_reports_payment(self):
        self.event(environment='PRODUCTION');self.assertEqual(StorePayment.objects.count(),0)
        e=CurrencyEvent.objects.create(event_id='pending',identity=self.identity,state='quarantined',payload={});project(e)
        self.assertEqual(StorePayment.objects.count(),0)
    def test_no_secret_or_subscriber_attributes_in_detail(self):
        self.event(subscriber_attributes={'secret':'private'})
        r=self.request(PaymentDetail,pk=StorePayment.objects.get().pk)
        self.assertNotIn('private',str(r.data));self.assertEqual(r.data['events'][0]['type'],'INITIAL_PURCHASE')
    def test_missing_wallet_is_unknown_not_zero(self):
        r=self.request(UserAssets,pk=self.identity.pk)
        self.assertIsNone(r.data['balance'])
    def test_currency_event_can_arrive_before_purchase(self):
        from .models import RechargeProduct
        RechargeProduct.objects.create(rc_project_id='project',apple_product_id='diamonds.60',rc_product_id='p',rc_package_id='p',units=60)
        self.event('VIRTUAL_CURRENCY_TRANSACTION',product_id='diamonds.60',source='in_app_purchase')
        row=StorePayment.objects.get();self.assertFalse(row.payment_confirmed);self.assertIsNone(row.amount)
        self.event('NON_RENEWING_PURCHASE',product_id='diamonds.60',price_in_purchased_currency=6)
        row.refresh_from_db();self.assertTrue(row.payment_confirmed);self.assertEqual(row.amount,6)
        self.assertEqual(StorePayment.objects.count(),1)
    def test_all_read_sections_and_inverted_dates(self):
        self.event()
        for section in ['users','redemption','activity','alerts','recharge']:
            r=self.request(Transactions,{'environment':'sandbox','section':section})
            self.assertEqual(r.status_code,200,section)
        r=self.request(Transactions,{'start':'2026-10-29T00:00:00Z','end':'2026-10-28T00:00:00Z'})
        self.assertEqual(r.status_code,400)
    def test_status_filters_and_customization_section(self):
        from .models import RechargeProduct,TopUpRecord
        RechargeProduct.objects.create(rc_project_id='project',apple_product_id='diamonds.60',rc_product_id='p',rc_package_id='p',units=60)
        self.event('NON_RENEWING_PURCHASE',product_id='diamonds.60',price_in_purchased_currency=6)
        for status,expected in [('pending_delivery',1),('confirmed',1),('refunded',0),('unknown_amount',0)]:
            response=self.request(Transactions,{'environment':'sandbox','section':'recharge','status':status})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.data['total'],expected)
        self.assertEqual(self.request(Transactions,{'environment':'sandbox','section':'customization'}).status_code,200)
    def test_delayed_grant_does_not_erase_refund(self):
        from .models import RechargeProduct
        from .topups import observe
        RechargeProduct.objects.create(rc_project_id='project',apple_product_id='diamonds.60',rc_product_id='p',rc_package_id='p',units=60)
        data={'transaction_id':'refund-first','store':'APP_STORE','product_id':'diamonds.60'}
        observe(self.identity,data,-60)
        row=observe(self.identity,data,60)
        self.assertEqual(row.state,'refunded');self.assertEqual(row.verified_units,-60)
