from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from types import SimpleNamespace
from .flags import enabled,sales_enabled
from .models import SalesControl,BillingAudit

@override_settings(DIAMOND_REDEMPTION_ENABLED=False,MEMBERSHIP_SALES_ENABLED=False,BILLING_SANDBOX_SALES_ENABLED=False)
class SalesControlTests(TestCase):
    def setUp(self):
        self.admin=get_user_model().objects.create_superuser(username='admin',email='a@example.test',password='test')
        self.client=APIClient();self.client.force_authenticate(self.admin)
        self.url='/api/v1/billing/manage/sales-settings/'
    def test_defaults_read_only_and_environment(self):
        r=self.client.get(self.url);self.assertEqual(r.status_code,200)
        self.assertFalse(r.data['diamond_redemption_enabled']);self.assertEqual(r.data['revision'],0)
        self.assertFalse(SalesControl.objects.exists())
    def test_changes_effective_for_all_readers_and_audited(self):
        r=self.client.patch(self.url,{'expected_revision':0,'diamond_redemption_enabled':True,'membership_sales_enabled':False,'reason':'开放钻石'},format='json')
        self.assertEqual(r.status_code,200)
        self.assertTrue(sales_enabled('DIAMOND_REDEMPTION_ENABLED'))
        self.assertTrue(enabled('DIAMOND_REDEMPTION_ENABLED',SimpleNamespace(wallet_domain='production')))
        self.assertFalse(sales_enabled('MEMBERSHIP_SALES_ENABLED'))
        self.assertEqual(BillingAudit.objects.get().detail['reason'],'开放钻石')
        SalesControl.objects.filter(pk=1).update(diamond_redemption_enabled=False)
        self.assertFalse(sales_enabled('DIAMOND_REDEMPTION_ENABLED'))
    def test_permission_and_optimistic_lock(self):
        SalesControl.objects.create(revision=2)
        r=self.client.patch(self.url,{'expected_revision':0,'diamond_redemption_enabled':True,'membership_sales_enabled':True,'reason':'stale'},format='json')
        self.assertEqual(r.status_code,409);self.assertFalse(BillingAudit.objects.exists())
        self.client.force_authenticate(get_user_model().objects.create_user(username='staff',is_staff=True))
        self.assertEqual(self.client.get(self.url).status_code,403)
        self.assertEqual(self.client.patch(self.url,{},format='json').status_code,403)
    def test_runtime_setting_overrides_environment_and_preserves_sandbox_override(self):
        SalesControl.objects.create(diamond_redemption_enabled=False)
        with override_settings(DIAMOND_REDEMPTION_ENABLED=True):self.assertFalse(sales_enabled('DIAMOND_REDEMPTION_ENABLED'))
        with override_settings(BILLING_SANDBOX_SALES_ENABLED=True):
            self.assertTrue(enabled('DIAMOND_REDEMPTION_ENABLED',SimpleNamespace(wallet_domain='sandbox')))
            self.assertFalse(enabled('DIAMOND_REDEMPTION_ENABLED',SimpleNamespace(wallet_domain='production')))
