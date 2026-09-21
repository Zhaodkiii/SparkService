import unittest

from common.middleware.request_logging_middleware import (
    _headers_for_log,
    _redact_credentials,
    _redact_sensitive_auth_body,
)


class RequestLoggingSensitiveAuthTests(unittest.TestCase):
    def test_auth_body_redacts_apple_credentials_recursively(self):
        body = {
            "identity_token": "apple-id-token",
            "authorization_code": "one-time-code",
            "nonce": "raw-nonce",
            "nested": {"refresh_token": "refresh-token"},
            "service_id": "cn.Zhaodk.Health.web",
        }

        redacted = _redact_sensitive_auth_body(body)

        self.assertEqual(redacted["identity_token"], "<redacted>")
        self.assertEqual(redacted["authorization_code"], "<redacted>")
        self.assertEqual(redacted["nonce"], "<redacted>")
        self.assertEqual(redacted["nested"]["refresh_token"], "<redacted>")
        self.assertEqual(redacted["service_id"], body["service_id"])

    def test_auth_headers_redact_cookie_and_authorization(self):
        redacted = _headers_for_log(
            {"Cookie": "session=secret", "Authorization": "Bearer secret", "Content-Type": "application/json"},
            redact_sensitive=True,
        )

        self.assertEqual(redacted["Cookie"], "<redacted>")
        self.assertEqual(redacted["Authorization"], "<redacted>")
        self.assertEqual(redacted["Content-Type"], "application/json")

    def test_headers_are_redacted_even_for_non_auth_routes(self):
        redacted = _headers_for_log(
            {
                "Authorization": "Bearer secret",
                "Idempotency-Key": "intent-secret",
                "Content-Type": "application/json",
            }
        )

        self.assertEqual(redacted["Authorization"], "<redacted>")
        self.assertEqual(redacted["Idempotency-Key"], "<redacted>")
        self.assertEqual(redacted["Content-Type"], "application/json")

    def test_credentials_are_redacted_recursively_for_all_json_bodies(self):
        body = {
            "api_key": "provider-secret",
            "nested": {
                "accessToken": "access-secret",
                "safe": "visible",
            },
            "items": [{"refresh_token": "refresh-secret"}],
        }

        redacted = _redact_credentials(body)

        self.assertEqual(redacted["api_key"], "<redacted>")
        self.assertEqual(redacted["nested"]["accessToken"], "<redacted>")
        self.assertEqual(redacted["items"][0]["refresh_token"], "<redacted>")
        self.assertEqual(redacted["nested"]["safe"], "visible")


if __name__ == "__main__":
    unittest.main()
