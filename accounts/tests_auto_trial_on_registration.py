from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import EmailOTP
from accounts.services.otp_service import OTPService
from ai_config.models import TrialApplication


class AutoTrialOnRegistrationTests(TestCase):
    def test_auto_trial_created_after_email_otp_registration(self):
        email = "auto-trial@example.com"
        otp_code = "123456"
        otp_id = "otp-auto-trial-1"

        EmailOTP.objects.create(
            otp_id=otp_id,
            email=email,
            code_hash=OTPService._hash_code(otp_code),
            expires_at=timezone.now() + timedelta(minutes=5),
            provider_uid="",
            bundle_id="com.sparkclient.ios",
            device_id="device-auto-trial",
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
            bundle_id="com.sparkclient.ios",
            device_id="device-auto-trial",
        )
        self.assertIn("access_token", result)

        user = get_user_model().objects.get(email=email)
        trial = TrialApplication.objects.get(user=user)
        self.assertEqual(trial.status, TrialApplication.Status.ACTIVE)
        self.assertTrue(trial.expires_at and trial.expires_at > timezone.now())
