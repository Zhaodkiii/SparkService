import unittest

from common.middleware.request_logging_middleware import _headers_for_log, _redact_sensitive_auth_body


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


if __name__ == "__main__":
    unittest.main()
