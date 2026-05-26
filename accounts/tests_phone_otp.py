from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounts.models import PhoneOTP, SocialIdentity
from accounts.services.otp_service import OTPService


@override_settings(
    OTP_WHITELIST_PHONES=["13800138000", "+8615000000001"],
    OTP_FIXED_WHITELIST_CODE="989898",
    ALIYUN_SMS_OTP_TEMPLATE_CODE="",
)
class PhoneOTPServiceTests(TestCase):
    def test_request_phone_otp_uses_fixed_code_for_whitelist_without_real_sms(self):
        result = OTPService.request_phone_otp(
            phone_number="13800138000",
            provider_uid="",
            bundle_id="com.sparkclient.ios",
            device_id="device-whitelist",
            ip_address="127.0.0.1",
            request_id="req-whitelist",
        )

        otp = PhoneOTP.objects.get(otp_id=result["otp_id"])
        self.assertEqual(otp.phone_number, "+8613800138000")
        self.assertEqual(otp.code_hash, OTPService._hash_code("989898"))

    def test_verify_phone_otp_creates_user_for_whitelist_phone(self):
        result = OTPService.request_phone_otp(
            phone_number="+8615000000001",
            provider_uid="",
            bundle_id="com.sparkclient.ios",
            device_id="device-login",
            ip_address="127.0.0.1",
            request_id="req-login",
        )

        verified = OTPService.verify_phone_otp_and_issue_tokens(
            otp_id=result["otp_id"],
            phone_number="+8615000000001",
            code="989898",
            request_id="req-login",
            ip_address="127.0.0.1",
            user_agent="unit-test",
            bundle_id="com.sparkclient.ios",
            device_id="device-login",
        )

        self.assertTrue(verified["access_token"])
        self.assertTrue(verified["is_new_user"])

        user = get_user_model().objects.get(id=verified["user_id"])
        self.assertTrue(
            SocialIdentity.objects.filter(
                user=user,
                bundle_id="com.sparkclient.ios",
                provider=SocialIdentity.Provider.PHONE,
                provider_uid="+8615000000001",
            ).exists()
        )

    def test_request_phone_otp_falls_back_to_dev_success_when_sms_config_missing(self):
        result = OTPService.request_phone_otp(
            phone_number="13900139000",
            provider_uid="",
            bundle_id="com.sparkclient.ios",
            device_id="device-dev",
            ip_address="127.0.0.1",
            request_id="req-dev",
        )

        otp = PhoneOTP.objects.get(otp_id=result["otp_id"])
        self.assertEqual(otp.phone_number, "+8613900139000")
