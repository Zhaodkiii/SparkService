"""Web 手机验证码登录的会话隔离测试（CHAT-WEB-020E）。

验证 Web 手机验证码登录只进入 AccountWebSession 会话域：
- Web 登录仅创建 AccountWebSession，不创建 TrustedDevice / AccountDeviceSession。
- Web token 携带 session_class=web + web_session_id，不含移动端 device 字段。
- 同一手机号命中同一 User，移动会话保持 ACTIVE，Web/移动会话并存。
- 序列化器拒绝一切移动端字段；开关关闭 / 服务 ID 未配置时返回 503。
"""

import jwt as pyjwt
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.auth.serializers import WebPhoneOTPRequestSerializer, WebPhoneOTPVerifySerializer
from accounts.models import (
    AccountDeviceSession,
    AccountWebSession,
    LoginAudit,
    PhoneOTP,
    SocialIdentity,
    TrustedDevice,
)
from accounts.services.device_session_service import DeviceSessionService
from accounts.services.web_phone_login_service import WebPhoneLoginService

User = get_user_model()

WEB_SERVICE_ID = "cn.Zhaodk.Health.web"
IDENTITY_SCOPE = "cn.Zhaodk.Health"
PHONE = "13800138000"
NORMALIZED_PHONE = "+8613800138000"
WHITELIST_CODE = "989898"


@override_settings(
    WEB_PHONE_OTP_LOGIN_ENABLED=True,
    WEB_SESSION_DOMAIN_ENABLED=True,
    WEB_AUTH_SERVICE_ID=WEB_SERVICE_ID,
    ACCOUNT_IDENTITY_SCOPE_ALIASES={WEB_SERVICE_ID: IDENTITY_SCOPE},
    OTP_WHITELIST_PHONES=[PHONE],
    OTP_FIXED_WHITELIST_CODE=WHITELIST_CODE,
)
class WebPhoneLoginSessionTests(TestCase):
    def _web_phone_login(self, *, phone=PHONE, code=WHITELIST_CODE, request_id="req-wp-1"):
        request = WebPhoneLoginService.request_otp(
            phone_number=phone,
            scene="login",
            ip_address="127.0.0.1",
            request_id=request_id,
        )
        return WebPhoneLoginService.verify_and_issue_tokens(
            otp_id=request["otp_id"],
            phone_number=phone,
            code=code,
            ip_address="127.0.0.1",
            user_agent="unit-test",
            request_id=request_id,
        )

    def test_web_phone_login_creates_web_session_and_no_device_records(self):
        result = self._web_phone_login()

        user = User.objects.get(id=result["user_id"])
        self.assertTrue(result["is_new_user"])
        self.assertEqual(result["session_class"], "web")

        # 隔离断言：Web 登录不得创建任何移动端会话/设备记录。
        self.assertEqual(AccountWebSession.objects.filter(user=user).count(), 1)
        self.assertEqual(AccountDeviceSession.objects.filter(user=user).count(), 0)
        self.assertEqual(TrustedDevice.objects.count(), 0)

        session = AccountWebSession.objects.get(user=user)
        self.assertEqual(session.status, AccountWebSession.Status.ACTIVE)
        self.assertTrue(session.refresh_jti_hash)
        self.assertNotEqual(session.refresh_jti_hash, "")

        identity = SocialIdentity.objects.get(
            bundle_id=IDENTITY_SCOPE,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid=NORMALIZED_PHONE,
        )
        self.assertEqual(identity.user, user)

        audit = LoginAudit.objects.filter(user=user, request_id="req-wp-1").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.bundle_id, WEB_SERVICE_ID)
        self.assertEqual(audit.raw_claims["channel"], "web")
        self.assertEqual(audit.raw_claims["session_class"], "web")

    def test_web_phone_login_token_claims_carry_web_session_only(self):
        result = self._web_phone_login()
        refresh = pyjwt.decode(result["refresh_token"], options={"verify_signature": False})
        self.assertEqual(refresh["session_class"], "web")
        self.assertIn("web_session_id", refresh)
        self.assertIn("web_session_version", refresh)
        self.assertNotIn("device_session_id", refresh)
        self.assertNotIn("device_id", refresh)
        self.assertNotIn("bundle_id", refresh)

    def test_web_phone_login_matches_existing_mobile_user_and_keeps_mobile_active(self):
        # 移动端先登录：同一手机号 + 同一身份作用域，并创建设备会话。
        mobile_user = User.objects.create_user(username="mobile_phone_user")
        mobile_user.set_unusable_password()
        mobile_user.save(update_fields=["password"])
        SocialIdentity.objects.create(
            user=mobile_user,
            bundle_id=IDENTITY_SCOPE,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid=NORMALIZED_PHONE,
        )
        TrustedDevice.objects.create(user=mobile_user, bundle_id=IDENTITY_SCOPE, device_id="dev-phone-1")
        DeviceSessionService.activate_session_on_login(
            user=mobile_user,
            bundle_id=IDENTITY_SCOPE,
            device_id="dev-phone-1",
            request_id="req-mobile-phone",
        )

        result = self._web_phone_login(request_id="req-wp-coexist")

        self.assertEqual(result["user_id"], mobile_user.id)
        self.assertFalse(result["is_new_user"])

        # 移动会话保持 ACTIVE，未被 Web 登录替换。
        mobile_session = AccountDeviceSession.objects.get(user=mobile_user)
        self.assertEqual(mobile_session.status, AccountDeviceSession.Status.ACTIVE)
        # Web 会话并存。
        self.assertEqual(
            AccountWebSession.objects.filter(user=mobile_user, status=AccountWebSession.Status.ACTIVE).count(),
            1,
        )

    def test_serializer_rejects_mobile_fields(self):
        request_serializer = WebPhoneOTPRequestSerializer(
            data={
                "phone_number": PHONE,
                "bundle_id": IDENTITY_SCOPE,
                "device_id": "dev-x",
                "device_secret": "secret",
                "user_id": 1,
                "provider_uid": "x",
            }
        )
        self.assertFalse(request_serializer.is_valid())
        for field in ("bundle_id", "device_id", "device_secret", "user_id", "provider_uid"):
            self.assertIn(field, request_serializer.errors)

        verify_serializer = WebPhoneOTPVerifySerializer(
            data={
                "otp_id": "otp-x",
                "phone_number": PHONE,
                "code": "123456",
                "bundle_id": IDENTITY_SCOPE,
                "device_id": "dev-x",
            }
        )
        self.assertFalse(verify_serializer.is_valid())
        for field in ("bundle_id", "device_id"):
            self.assertIn(field, verify_serializer.errors)

    def test_disabled_flag_returns_503(self):
        from common.exceptions import APIError

        with override_settings(WEB_PHONE_OTP_LOGIN_ENABLED=False):
            with self.assertRaises(APIError) as ctx:
                WebPhoneLoginService.request_otp(
                    phone_number=PHONE,
                    scene="login",
                    ip_address="127.0.0.1",
                    request_id="req-wp-disabled",
                )
        self.assertEqual(ctx.exception.code, 50375)

    def test_misconfigured_service_id_returns_503(self):
        from common.exceptions import APIError

        with override_settings(WEB_AUTH_SERVICE_ID=""):
            with self.assertRaises(APIError) as ctx:
                WebPhoneLoginService.verify_and_issue_tokens(
                    otp_id="otp-x",
                    phone_number=PHONE,
                    code=WHITELIST_CODE,
                    ip_address="127.0.0.1",
                    user_agent="unit-test",
                    request_id="req-wp-bad",
                )
        self.assertEqual(ctx.exception.code, 50376)

    def test_phone_otp_is_marked_used_after_web_verify(self):
        result = self._web_phone_login(request_id="req-wp-used")
        otp = PhoneOTP.objects.get(otp_id=result["otp_id"])
        self.assertIsNotNone(otp.used_at)


@override_settings(
    WEB_PHONE_OTP_LOGIN_ENABLED=True,
    WEB_SESSION_DOMAIN_ENABLED=True,
    WEB_AUTH_SERVICE_ID=WEB_SERVICE_ID,
    ACCOUNT_IDENTITY_SCOPE_ALIASES={WEB_SERVICE_ID: IDENTITY_SCOPE},
    OTP_WHITELIST_PHONES=[PHONE],
    OTP_FIXED_WHITELIST_CODE=WHITELIST_CODE,
)
class WebPhoneApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_request_endpoint_uses_whitelist_without_real_sms(self):
        response = self.client.post(
            "/api/v1/auth/phone/web/otp/request/",
            data={"phone_number": PHONE, "scene": "login"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json().get("data") or response.json()
        self.assertIn("otp_id", data)
        otp = PhoneOTP.objects.get(otp_id=data["otp_id"])
        self.assertEqual(otp.send_status, PhoneOTP.SendStatus.ACCEPTED)

    def test_request_endpoint_rejects_mobile_fields(self):
        response = self.client.post(
            "/api/v1/auth/phone/web/otp/request/",
            data={"phone_number": PHONE, "bundle_id": IDENTITY_SCOPE, "device_id": "dev-x"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_verify_endpoint_issues_web_session_token(self):
        request_response = self.client.post(
            "/api/v1/auth/phone/web/otp/request/",
            data={"phone_number": PHONE, "scene": "login"},
            format="json",
        )
        request_data = request_response.json().get("data") or request_response.json()

        response = self.client.post(
            "/api/v1/auth/phone/web/otp/verify/",
            data={"otp_id": request_data["otp_id"], "phone_number": PHONE, "code": WHITELIST_CODE},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json().get("data") or response.json()
        self.assertEqual(data["session_class"], "web")
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)

        user = User.objects.get(id=data["user_id"])
        self.assertEqual(AccountWebSession.objects.filter(user=user).count(), 1)
        self.assertEqual(AccountDeviceSession.objects.filter(user=user).count(), 0)
        self.assertEqual(TrustedDevice.objects.count(), 0)