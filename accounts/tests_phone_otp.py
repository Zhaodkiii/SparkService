import json
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from types import SimpleNamespace
from unittest.mock import patch

from common.exceptions import APIError
from accounts.models import PhoneOTP, SocialIdentity
from accounts.services.otp_service import OTPService
from notification_center.models import NotificationMessage


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

    @patch("notification_center.services.AliyunSMSProvider.send_login_code")
    @patch("notification_center.services.AliyunSMSProvider.otp_readiness_error", return_value="")
    def test_login_phone_otp_uses_bundle_specific_social_identity(self, _readiness, mocked_send):
        User = get_user_model()
        user_a = User.objects.create_user(username="bundle-a-user", password="x")
        user_b = User.objects.create_user(username="bundle-b-user", password="x")
        SocialIdentity.objects.create(
            user=user_a,
            bundle_id="cn.Zhaodk.Health",
            provider=SocialIdentity.Provider.PHONE,
            provider_uid="+8615385056020",
        )
        SocialIdentity.objects.create(
            user=user_b,
            bundle_id="cn.zdk.SupportClient",
            provider=SocialIdentity.Provider.PHONE,
            provider_uid="+8615385056020",
        )
        mocked_send.return_value = SimpleNamespace(
            accepted=True,
            unknown=False,
            reason="",
            biz_id="biz",
            request_id="req",
            code="OK",
            status="accepted",
            payload={},
        )

        result = OTPService.request_phone_otp(
            phone_number="+8615385056020",
            provider_uid="",
            bundle_id="cn.Zhaodk.Health",
            device_id="device-health",
            ip_address="127.0.0.1",
            request_id="req-health",
            scene="login",
        )

        message = NotificationMessage.objects.select_related("intent", "user").order_by("-id").first()
        self.assertIsNotNone(message)
        self.assertEqual(message.user_id, user_a.id)
        self.assertEqual(message.intent.business_scene, "account.auth.login_otp_requested")
        self.assertEqual(message.intent.business_domain, "account")
        self.assertEqual(message.intent.business_type, "account.auth")
        self.assertEqual(message.body, "")
        self.assertNotIn("template_param", message.payload)
        otp = PhoneOTP.objects.get(otp_id=result["otp_id"])
        self.assertEqual(otp.scene, "account.auth.login_otp_requested")
        self.assertEqual(otp.requested_user_id, user_a.id)
        self.assertEqual(otp.resolved_identity.user_id, user_a.id)
        self.assertEqual(otp.send_status, PhoneOTP.SendStatus.ACCEPTED)

    @patch("notification_center.services.AliyunSMSProvider.send_login_code")
    @patch("notification_center.services.AliyunSMSProvider.otp_readiness_error", return_value="")
    def test_phone_otp_provider_submit_failure_returns_error_and_invalidates_otp(self, _readiness, mocked_send):
        mocked_send.return_value = SimpleNamespace(
            accepted=False,
            unknown=False,
            reason="isv.BUSINESS_LIMIT_CONTROL:触发天级流控Permits:10",
            biz_id="",
            request_id="provider-limited",
            code="isv.BUSINESS_LIMIT_CONTROL",
            status="failed",
            payload={},
        )

        with self.assertRaises(APIError) as ctx:
            OTPService.request_phone_otp(
                phone_number="+8618255099136",
                provider_uid="",
                bundle_id="cn.Zhaodk.Health",
                device_id="device-health",
                ip_address="127.0.0.1",
                request_id="req-provider-limited",
                scene="login",
            )

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.code, 42902)
        self.assertEqual(ctx.exception.msg, "sms_send_rate_limited")
        self.assertEqual(ctx.exception.details["error_type"], "sms_send_rate_limited")
        self.assertEqual(ctx.exception.details["reason"], "isv.BUSINESS_LIMIT_CONTROL:触发天级流控Permits:10")
        otp = PhoneOTP.objects.get(request_id="req-provider-limited")
        self.assertEqual(otp.send_status, PhoneOTP.SendStatus.SUBMIT_FAILED)
        self.assertIsNotNone(otp.invalidated_at)
        self.assertEqual(otp.provider_request_id, "provider-limited")
        self.assertEqual(otp.send_error_code, "isv.BUSINESS_LIMIT_CONTROL:触发天级流控Permits:10")

    def test_request_phone_otp_returns_localizable_rate_limit_error(self):
        PhoneOTP.objects.create(
            otp_id="recent-otp",
            phone_number="+8618255099136",
            code_hash=OTPService._hash_code("123456"),
            expires_at=timezone.now() + timedelta(minutes=5),
            bundle_id="cn.Zhaodk.Health",
            device_id="device-health",
        )

        with self.assertRaises(APIError) as ctx:
            OTPService.request_phone_otp(
                phone_number="+8618255099136",
                provider_uid="",
                bundle_id="cn.Zhaodk.Health",
                device_id="device-health",
                ip_address="127.0.0.1",
                request_id="req-rate-limited",
                scene="login",
            )

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.code, 42901)
        self.assertEqual(ctx.exception.msg, "otp_requested_too_frequently")
        self.assertEqual(ctx.exception.details["error_type"], "otp_requested_too_frequently")
        self.assertEqual(ctx.exception.details["reason"], "otp_requested_too_frequently")

    @patch("accounts.services.otp_service.NotificationCenterService.send_phone_otp")
    def test_request_phone_otp_rejects_non_china_region_before_creating_otp(self, mocked_send_phone_otp):
        with self.assertRaises(APIError) as ctx:
            OTPService.request_phone_otp(
                phone_number="+14155552671",
                provider_uid="",
                bundle_id="cn.Zhaodk.Health",
                device_id="device-us",
                ip_address="127.0.0.1",
                request_id="req-us",
                scene="login",
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.code, 40033)
        self.assertEqual(ctx.exception.msg, "phone_region_not_supported")
        self.assertEqual(ctx.exception.details["error_type"], "phone_region_not_supported")
        self.assertEqual(ctx.exception.details["reason"], "phone_region_not_supported")
        self.assertEqual(ctx.exception.details["phone_region"], "US")
        self.assertEqual(ctx.exception.details["dial_code"], "+1")
        self.assertEqual(ctx.exception.details["supported_regions"], ["CN"])
        self.assertEqual(ctx.exception.details["supported_dial_codes"], ["+86"])
        self.assertFalse(PhoneOTP.objects.filter(request_id="req-us").exists())
        mocked_send_phone_otp.assert_not_called()

    def test_phone_otp_request_api_returns_localizable_non_china_error(self):
        response = self.client.post(
            "/api/v1/otp/phone/request/",
            data=json.dumps({
                "phone_number": "+85251234567",
                "provider_uid": "",
                "scene": "login",
                "bundle_id": "cn.Zhaodk.Health",
                "device_id": "device-hk",
            }),
            content_type="application/json",
            HTTP_X_REQUEST_ID="req-api-hk",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], 40033)
        self.assertEqual(response.data["msg"], "phone_region_not_supported")
        self.assertEqual(response.data["data"]["error_type"], "phone_region_not_supported")
        self.assertEqual(response.data["data"]["reason"], "phone_region_not_supported")
        self.assertEqual(response.data["data"]["phone_region"], "HK")
        self.assertEqual(response.data["data"]["dial_code"], "+852")
        self.assertEqual(response.data["data"]["request_id"], "req-api-hk")
        self.assertFalse(PhoneOTP.objects.filter(request_id="req-api-hk").exists())

    def test_phone_otp_verify_rejects_invalidated_submit_failed_otp(self):
        otp = PhoneOTP.objects.create(
            otp_id="failed-otp",
            phone_number="+8618255099136",
            code_hash=OTPService._hash_code("123456"),
            expires_at=timezone.now() + timedelta(minutes=5),
            bundle_id="cn.Zhaodk.Health",
            device_id="device-health",
            send_status=PhoneOTP.SendStatus.SUBMIT_FAILED,
            invalidated_at=timezone.now(),
        )

        with self.assertRaises(APIError) as ctx:
            OTPService.verify_phone_otp_and_issue_tokens(
                otp_id=otp.otp_id,
                phone_number="+8618255099136",
                code="123456",
                request_id="req-verify-failed",
                ip_address="127.0.0.1",
                user_agent="unit-test",
                bundle_id="cn.Zhaodk.Health",
                device_id="device-health",
            )

        self.assertEqual(ctx.exception.code, 40045)

    def test_request_phone_otp_raises_when_sms_config_missing(self):
        with self.assertRaises(APIError) as ctx:
            OTPService.request_phone_otp(
                phone_number="13900139000",
                provider_uid="",
                bundle_id="com.sparkclient.ios",
                device_id="device-dev",
                ip_address="127.0.0.1",
                request_id="req-dev",
            )

        self.assertEqual(ctx.exception.code, 50231)
        self.assertEqual(ctx.exception.msg, "sms_send_failed")

    @patch("accounts.services.otp_service.NotificationCenterService.send_phone_otp", return_value=(True, "", "message-id"))
    def test_first_login_without_social_identity_does_not_bind_user(self, mocked_send_phone_otp):
        result = OTPService.request_phone_otp(
            phone_number="+8613900139000",
            provider_uid="",
            bundle_id="cn.Zhaodk.Health",
            device_id="device-new-user",
            ip_address="127.0.0.1",
            request_id="req-new-user",
            scene="login",
        )

        otp = PhoneOTP.objects.get(otp_id=result["otp_id"])
        self.assertEqual(otp.scene, "account.auth.login_otp_requested")
        self.assertIsNone(otp.requested_user_id)
        self.assertIsNone(otp.resolved_identity_id)
        self.assertIsNone(mocked_send_phone_otp.call_args.kwargs["user_id"])

    def test_account_deactivation_otp_requires_user_id(self):
        with self.assertRaises(APIError) as ctx:
            OTPService.request_phone_otp(
                phone_number="+8613800138000",
                provider_uid="",
                bundle_id="cn.Zhaodk.Health",
                device_id="device-deactivation",
                ip_address="127.0.0.1",
                request_id="req-deactivation-missing-user",
                scene="account_deactivation",
                actor_user_id=1,
            )

        self.assertEqual(ctx.exception.code, 40061)

    def test_account_deactivation_otp_requires_matching_user_context(self):
        User = get_user_model()
        user = User.objects.create_user(username="deactivation-user", password="x")
        SocialIdentity.objects.create(
            user=user,
            bundle_id="cn.Zhaodk.Health",
            provider=SocialIdentity.Provider.PHONE,
            provider_uid="+8613800138000",
        )

        with self.assertRaises(APIError) as ctx:
            OTPService.request_phone_otp(
                phone_number="+8613800138000",
                provider_uid="",
                bundle_id="cn.Zhaodk.Health",
                device_id="device-deactivation",
                ip_address="127.0.0.1",
                request_id="req-deactivation",
                scene="account_deactivation",
                user_id=user.id,
                actor_user_id=user.id + 1,
            )

        self.assertEqual(ctx.exception.code, 40361)
