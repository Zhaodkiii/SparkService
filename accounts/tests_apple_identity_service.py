import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import SimpleTestCase, override_settings

from accounts.services.apple_identity_service import AppleIdentityService
from common.exceptions import APIError


class AppleIdentityServiceTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.private_key.public_key()))
        cls.public_jwk.update({"kid": "test-kid", "alg": "RS256", "use": "sig"})

    def _token(self, *, audience: str, issued_delta: timedelta = timedelta(seconds=-1)) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "iss": "https://appleid.apple.com",
                "aud": audience,
                "sub": "apple-subject-1",
                "iat": now + issued_delta,
                "exp": now + timedelta(hours=1),
            },
            self.private_key,
            algorithm="RS256",
            headers={"kid": "test-kid", "alg": "RS256"},
        )

    @override_settings(APPLE_IDENTITY_TOKEN_LEEWAY_SECONDS=30)
    @patch.object(AppleIdentityService, "_load_jwks")
    def test_verify_identity_token_accepts_small_iat_clock_skew(self, mock_load_jwks):
        mock_load_jwks.return_value = [self.public_jwk]
        token = self._token(audience="cn.Zhaodk.Health", issued_delta=timedelta(seconds=2))

        payload, matched_audience = AppleIdentityService.verify_identity_token(
            token,
            audiences=["cn.Zhaodk.Health"],
        )

        self.assertEqual(payload["sub"], "apple-subject-1")
        self.assertEqual(matched_audience, "cn.Zhaodk.Health")

    @override_settings(APPLE_IDENTITY_TOKEN_LEEWAY_SECONDS=0)
    @patch.object(AppleIdentityService, "_load_jwks")
    def test_verify_identity_token_reports_time_error_separately(self, mock_load_jwks):
        mock_load_jwks.return_value = [self.public_jwk]
        token = self._token(audience="cn.Zhaodk.Health", issued_delta=timedelta(seconds=60))

        with self.assertRaises(APIError) as raised:
            AppleIdentityService.verify_identity_token(token, audiences=["cn.Zhaodk.Health"])

        self.assertEqual(raised.exception.msg, "apple_token_time_invalid")
        self.assertEqual(raised.exception.code, 40125)
        self.assertIn("not yet valid", raised.exception.details["error"])

    @override_settings(APPLE_IDENTITY_TOKEN_LEEWAY_SECONDS=30)
    @patch.object(AppleIdentityService, "_load_jwks")
    def test_verify_identity_token_keeps_audience_mismatch_for_wrong_audience(self, mock_load_jwks):
        mock_load_jwks.return_value = [self.public_jwk]
        token = self._token(audience="com.other.app")

        with self.assertRaises(APIError) as raised:
            AppleIdentityService.verify_identity_token(token, audiences=["cn.Zhaodk.Health"])

        self.assertEqual(raised.exception.msg, "apple_audience_mismatch")
        self.assertEqual(raised.exception.code, 40122)
        self.assertEqual(raised.exception.details["allowed_audiences"], ["cn.Zhaodk.Health"])
