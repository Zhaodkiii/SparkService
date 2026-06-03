from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import EmailOTP, TrustedDevice
from accounts.services.otp_service import OTPService
from ai_config.models import TrialApplication, TrialApplicationRequest


class AutoTrialOnRegistrationTests(TestCase):
    def test_auto_trial_created_after_email_otp_registration(self):
        email = "auto-trial@example.com"
        otp_code = "123456"
        otp_id = "otp-auto-trial-1"
        bundle_id = "com.sparkclient.ios"
        device_id = "device-auto-trial"

        TrustedDevice.objects.create(
            bundle_id=bundle_id,
            device_id=device_id,
            country_code="CN",
        )

        EmailOTP.objects.create(
            otp_id=otp_id,
            email=email,
            code_hash=OTPService._hash_code(otp_code),
            expires_at=timezone.now() + timedelta(minutes=5),
            provider_uid="",
            bundle_id=bundle_id,
            device_id=device_id,
            ip_address="127.0.0.1",
            request_id="req-auto-trial",
        )

        result = OTPService.verify_email_otp_and_issue_tokens(
            otp_id=otp_id,
            email=email,
            code=otp_code,
            request_id="req-auto-trial",
            ip_address="127.0.0.1",
            user_agent="unit-test",
            bundle_id=bundle_id,
            device_id=device_id,
        )
        self.assertIn("access_token", result)
        self.assertTrue(result["is_pro"])

        user = get_user_model().objects.get(email=email)
        trial = TrialApplication.objects.get(user=user)
        self.assertEqual(trial.status, TrialApplication.Status.ACTIVE)
        self.assertTrue(trial.expires_at and trial.expires_at > timezone.now())


class SameDeviceMultiUserAutoTrialTests(TestCase):
    """AI-CONFIG-000005: 同设备安装换用户后，新用户仍可按用户维度自动发放 Pro。"""

    bundle_id = "com.sparkclient.ios"
    device_id = "shared-install-0001"

    def _issue_email_otp(self, *, email: str, otp_id: str, code: str = "123456"):
        EmailOTP.objects.create(
            otp_id=otp_id,
            email=email,
            code_hash=OTPService._hash_code(code),
            expires_at=timezone.now() + timedelta(minutes=5),
            provider_uid="",
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            ip_address="127.0.0.1",
            request_id=f"req-{otp_id}",
        )

    def _login_email_otp(self, *, email: str, otp_id: str, code: str = "123456"):
        return OTPService.verify_email_otp_and_issue_tokens(
            otp_id=otp_id,
            email=email,
            code=code,
            request_id=f"req-{otp_id}",
            ip_address="127.0.0.1",
            user_agent="unit-test",
            bundle_id=self.bundle_id,
            device_id=self.device_id,
        )

    def test_second_and_third_user_on_same_device_get_auto_trial_after_first_user_logout(self):
        TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=None,
            country_code="CN",
        )

        email_a = "user-a1@example.com"
        self._issue_email_otp(email=email_a, otp_id="otp-a1")
        result_a = self._login_email_otp(email=email_a, otp_id="otp-a1")
        self.assertTrue(result_a["is_pro"])

        user_a = get_user_model().objects.get(email=email_a)
        device_a = TrustedDevice.objects.get(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=user_a,
        )
        self.assertEqual(device_a.country_code, "CN")
        self.assertEqual(TrialApplication.objects.get(user=user_a).status, TrialApplication.Status.ACTIVE)

        device_a.is_revoked = True
        device_a.save(update_fields=["is_revoked", "last_seen"])

        email_b = "user-b1@example.com"
        self._issue_email_otp(email=email_b, otp_id="otp-b1")
        result_b = self._login_email_otp(email=email_b, otp_id="otp-b1")
        self.assertTrue(result_b["is_pro"])

        user_b = get_user_model().objects.get(email=email_b)
        device_b = TrustedDevice.objects.get(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=user_b,
            is_revoked=False,
        )
        self.assertEqual(device_b.country_code, "")
        trial_b = TrialApplication.objects.get(user=user_b)
        self.assertEqual(trial_b.status, TrialApplication.Status.ACTIVE)
        self.assertTrue(
            TrialApplicationRequest.objects.filter(
                user=user_b,
                source=TrialApplicationRequest.Source.AUTO,
            ).exists()
        )

        device_b.is_revoked = True
        device_b.save(update_fields=["is_revoked", "last_seen"])

        email_c = "user-c1@example.com"
        self._issue_email_otp(email=email_c, otp_id="otp-c1")
        result_c = self._login_email_otp(email=email_c, otp_id="otp-c1")
        self.assertTrue(result_c["is_pro"])

        user_c = get_user_model().objects.get(email=email_c)
        self.assertEqual(
            TrialApplication.objects.get(user=user_c).status,
            TrialApplication.Status.ACTIVE,
        )

    def test_second_user_skips_auto_trial_when_historical_device_country_not_cn(self):
        User = get_user_model()
        user_a = User.objects.create_user(username="us_a", email="us-a@example.com", password="x")
        TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=user_a,
            country_code="US",
            is_revoked=True,
        )

        email_b = "us-b@example.com"
        self._issue_email_otp(email=email_b, otp_id="otp-us-b")
        result_b = self._login_email_otp(email=email_b, otp_id="otp-us-b")

        self.assertFalse(result_b["is_pro"])
        user_b = User.objects.get(email=email_b)
        with self.assertRaises(TrialApplication.DoesNotExist):
            TrialApplication.objects.get(user=user_b, status=TrialApplication.Status.ACTIVE)
