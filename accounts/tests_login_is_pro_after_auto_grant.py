from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import EmailOTP, TrustedDevice
from accounts.services.login_service import LoginService
from accounts.services.otp_service import OTPService
from ai_config.models import TrialApplication


@override_settings(APPLE_ALLOWED_BUNDLE_IDS=["com.sparkclient.ios"])
class LoginIsProAfterAutoGrantTests(TestCase):
    bundle_id = "com.sparkclient.ios"
    device_id = "device-cn-login-test"

    def _create_cn_trusted_device(self):
        TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            country_code="CN",
        )

    @patch("accounts.services.login_service.AppleIdentityService.verify_identity_token")
    def test_apple_login_returns_is_pro_true_after_cn_auto_grant(self, mock_verify):
        mock_verify.return_value = (
            {"sub": "apple-sub-cn-1", "email": "cn-auto@example.com"},
            self.bundle_id,
        )
        self._create_cn_trusted_device()

        result = LoginService.authenticate_apple_and_issue_tokens(
            identity_token="fake-token",
            bundle_id=self.bundle_id,
            nonce="",
            user_identifier="apple-user-1",
            email="cn-auto@example.com",
            full_name="CN User",
            ip_address="127.0.0.1",
            user_agent="unit-test",
            device_id=self.device_id,
            request_id="req-apple-cn",
        )

        self.assertTrue(result["is_pro"])
        user = get_user_model().objects.get(id=result["user_id"])
        trial = TrialApplication.objects.get(user=user)
        self.assertEqual(trial.status, TrialApplication.Status.ACTIVE)

    @patch("accounts.services.login_service.AppleIdentityService.verify_identity_token")
    def test_apple_login_returns_is_pro_false_when_device_not_cn(self, mock_verify):
        mock_verify.return_value = (
            {"sub": "apple-sub-us-1", "email": "us@example.com"},
            self.bundle_id,
        )
        TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id="device-us-login-test",
            country_code="US",
        )

        result = LoginService.authenticate_apple_and_issue_tokens(
            identity_token="fake-token",
            bundle_id=self.bundle_id,
            nonce="",
            user_identifier="apple-user-2",
            email="us@example.com",
            full_name="US User",
            ip_address="127.0.0.1",
            user_agent="unit-test",
            device_id="device-us-login-test",
            request_id="req-apple-us",
        )

        self.assertFalse(result["is_pro"])
        user = get_user_model().objects.get(id=result["user_id"])
        with self.assertRaises(TrialApplication.DoesNotExist):
            TrialApplication.objects.get(user=user, status=TrialApplication.Status.ACTIVE)

    def test_email_otp_login_returns_is_pro_true_after_cn_auto_grant(self):
        email = "cn-otp-auto@example.com"
        otp_code = "654321"
        otp_id = "otp-cn-is-pro"
        self._create_cn_trusted_device()

        EmailOTP.objects.create(
            otp_id=otp_id,
            email=email,
            code_hash=OTPService._hash_code(otp_code),
            expires_at=timezone.now() + timedelta(minutes=5),
            provider_uid="",
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            ip_address="127.0.0.1",
            request_id="req-otp-cn",
        )

        result = OTPService.verify_email_otp_and_issue_tokens(
            otp_id=otp_id,
            email=email,
            code=otp_code,
            request_id="req-otp-cn",
            ip_address="127.0.0.1",
            user_agent="unit-test",
            bundle_id=self.bundle_id,
            device_id=self.device_id,
        )

        self.assertTrue(result["is_pro"])
        user = get_user_model().objects.get(email=email)
        trial = TrialApplication.objects.get(user=user)
        self.assertEqual(trial.status, TrialApplication.Status.ACTIVE)

    @patch("accounts.services.login_service.AppleIdentityService.verify_identity_token")
    def test_apple_login_existing_pro_user_still_returns_is_pro_true(self, mock_verify):
        mock_verify.return_value = (
            {"sub": "apple-sub-pro-1", "email": "pro@example.com"},
            self.bundle_id,
        )
        self._create_cn_trusted_device()

        User = get_user_model()
        user = User.objects.create_user(username="pro_user", email="pro@example.com", password="unused")
        now = timezone.now()
        TrialApplication.objects.create(
            user=user,
            status=TrialApplication.Status.ACTIVE,
            grant_source=TrialApplication.GrantSource.AUTO,
            started_at=now,
            expires_at=now + timedelta(days=15),
            applied_at=now,
            approved_at=now,
        )

        from accounts.models import SocialIdentity

        SocialIdentity.objects.create(
            user=user,
            bundle_id=self.bundle_id,
            provider=SocialIdentity.Provider.APPLE,
            provider_uid="apple-sub-pro-1",
        )

        result = LoginService.authenticate_apple_and_issue_tokens(
            identity_token="fake-token",
            bundle_id=self.bundle_id,
            nonce="",
            user_identifier="apple-user-pro",
            email="pro@example.com",
            full_name="Pro User",
            ip_address="127.0.0.1",
            user_agent="unit-test",
            device_id=self.device_id,
            request_id="req-apple-pro",
        )

        self.assertTrue(result["is_pro"])

    def test_email_otp_second_user_on_same_install_returns_is_pro_via_historical_cn_device(self):
        """AI-CONFIG-000005: A1 退出后 B1 无匿名行、当前设备行无 country 时仍应 is_pro=true。"""
        User = get_user_model()
        user_a = User.objects.create_user(username="hist_a", email="hist-a@example.com", password="x")
        TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=user_a,
            country_code="CN",
            is_revoked=True,
        )

        email_b = "hist-b@example.com"
        otp_code = "112233"
        otp_id = "otp-hist-b"
        EmailOTP.objects.create(
            otp_id=otp_id,
            email=email_b,
            code_hash=OTPService._hash_code(otp_code),
            expires_at=timezone.now() + timedelta(minutes=5),
            provider_uid="",
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            ip_address="127.0.0.1",
            request_id="req-hist-b",
        )

        result = OTPService.verify_email_otp_and_issue_tokens(
            otp_id=otp_id,
            email=email_b,
            code=otp_code,
            request_id="req-hist-b",
            ip_address="127.0.0.1",
            user_agent="unit-test",
            bundle_id=self.bundle_id,
            device_id=self.device_id,
        )

        self.assertTrue(result["is_pro"])
        user_b = User.objects.get(email=email_b)
        device_b = TrustedDevice.objects.get(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=user_b,
            is_revoked=False,
        )
        self.assertEqual(device_b.country_code, "")
        self.assertEqual(
            TrialApplication.objects.get(user=user_b).status,
            TrialApplication.Status.ACTIVE,
        )
