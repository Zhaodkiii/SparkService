from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from .provider import RevenueCat, ProviderResult

@override_settings(REVENUECAT_PROJECT_ID='test')
class SubscriptionPaginationTests(SimpleTestCase):
    @patch.object(RevenueCat, 'request')
    def test_all_pages_are_returned(self, request):
        request.side_effect = [
            ProviderResult(200, {'items': [{'id': 'first'}], 'next_page': 'https://api.revenuecat.com/v2/projects/test/customers/customer/subscriptions?starting_after=first'}),
            ProviderResult(200, {'items': [{'id': 'second'}]})]
        result = RevenueCat().subscriptions(SimpleNamespace(rc_app_user_id='customer', wallet_domain='sandbox'))
        self.assertEqual(result.body['items'], [{'id': 'first'}, {'id': 'second'}])
        self.assertEqual(request.call_count, 2)

    @patch.object(RevenueCat, 'request')
    def test_foreign_pagination_is_rejected(self, request):
        request.return_value = ProviderResult(200, {'items': [], 'next_page': 'https://other.test/v2/projects/test/customers/customer/subscriptions'})
        result = RevenueCat().subscriptions(SimpleNamespace(rc_app_user_id='customer', wallet_domain='sandbox'))
        self.assertEqual(result.status, 502)
        self.assertEqual(request.call_count, 1)
