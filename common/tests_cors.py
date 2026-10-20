from django.test import SimpleTestCase, override_settings


@override_settings(
    CORS_ALLOW_ALL_ORIGINS=False,
    CORS_ALLOWED_ORIGINS=['http://localhost:6018'],
)
class CustomizationCORSPreflightTests(SimpleTestCase):
    def preflight(self, action, origin='http://localhost:6018'):
        return self.client.options(
            '/api/admin/v1/diary-customizations/requests/'
            '19a0040d-d537-46ee-ae59-16786cbd2c8c/' + action + '/',
            HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type,idempotency-key',
        )

    def test_business_actions_allow_idempotency_header_from_configured_admin_origin(self):
        # A 200 OPTIONS alone is insufficient: browsers also enforce allowed headers.
        for action in ('accept', 'request-info', 'production', 'deliver', 'cancel'):
            with self.subTest(action=action):
                response = self.preflight(action)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Access-Control-Allow-Origin'], 'http://localhost:6018')
                allowed = {h.strip().lower() for h in response['Access-Control-Allow-Headers'].split(',')}
                self.assertTrue({'authorization', 'content-type', 'idempotency-key'} <= allowed)
                self.assertIn('POST', response['Access-Control-Allow-Methods'])

    def test_unconfigured_origin_is_still_rejected(self):
        response = self.preflight('accept', origin='https://untrusted.example')
        self.assertNotIn('Access-Control-Allow-Origin', response)
