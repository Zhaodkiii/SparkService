import json
from unittest.mock import patch
from django.http import JsonResponse
from django.test import SimpleTestCase, RequestFactory
from common.middleware.catalog_cache import CatalogConditionalGetMiddleware


class CatalogCacheTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.body = {'items': [{'id': '1', 'version': 1, 'access': {'can_use': True},
                               'url': 'https://a.aliyuncs.com/a?Expires=900&Signature=old',
                               'sha256': 'abc', 'expires_at': 'old'}]}
        self.calls = 0

    def response(self, path='/api/v1/fonts/families/', etag=None, status=200, method='get', **headers):
        def view(request):
            self.calls += 1
            return JsonResponse(self.body, status=status)
        if etag:
            headers['HTTP_IF_NONE_MATCH'] = etag
        request = getattr(self.factory, method)(path, **headers)
        return CatalogConditionalGetMiddleware(view)(request)

    @patch('common.middleware.catalog_cache.time.time', return_value=1201)
    def test_signature_churn_304_but_rights_change_200(self, clock):
        first = self.response()
        self.body['items'][0].update(url='https://a.aliyuncs.com/a?Expires=950&Signature=new', expires_at='new')
        second = self.response(etag=first['ETag'])
        self.assertEqual(second.status_code, 304)
        self.assertEqual(second.content, b'')
        self.assertEqual(self.calls, 2)  # authorization/visibility still evaluated
        self.body['items'][0]['access']['can_use'] = False
        self.assertEqual(self.response(etag=first['ETag']).status_code, 200)

    def test_window_rotates_before_signed_url_expiry(self):
        with patch('common.middleware.catalog_cache.time.time', return_value=1201):
            first = self.response()
        with patch('common.middleware.catalog_cache.time.time', return_value=1801):
            self.assertEqual(self.response(etag=first['ETag']).status_code, 200)

    @patch('common.middleware.catalog_cache.time.time', return_value=1201)
    def test_account_query_and_billing_isolation(self, clock):
        first = self.response(HTTP_AUTHORIZATION='Bearer a', HTTP_X_BILLING_SESSION='one')
        self.assertEqual(self.response(etag=first['ETag'], HTTP_AUTHORIZATION='Bearer b').status_code, 200)
        self.assertEqual(self.response(etag=first['ETag'], HTTP_AUTHORIZATION='Bearer a', HTTP_X_BILLING_SESSION='two').status_code, 200)
        self.assertEqual(self.response(path='/api/v1/fonts/families/?page=2', etag=first['ETag']).status_code, 200)
        self.assertIn('Authorization', first['Vary'])
        self.assertEqual(first['Cache-Control'], 'private, max-age=300')

    def test_mutations_errors_and_live_endpoints_excluded(self):
        for path in ['/api/v1/billing/wallet/', '/api/v1/fonts/download-plans/',
                     '/api/v1/support/summary/', '/api/v1/materials/previews/resolve/',
                     '/api/v1/support/tickets/']:
            self.assertFalse(self.response(path).has_header('ETag'))
        self.assertFalse(self.response(method='post').has_header('ETag'))
        self.assertFalse(self.response(status=403).has_header('ETag'))

    def test_no_store_preserved(self):
        def view(request):
            response = JsonResponse(self.body)
            response['Cache-Control'] = 'no-store'
            return response
        response = CatalogConditionalGetMiddleware(view)(self.factory.get('/api/v1/fonts/families/'))
        self.assertFalse(response.has_header('ETag'))
