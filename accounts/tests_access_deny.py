from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from unittest.mock import patch

from accounts.models import AccessDenyEntry, SocialIdentity
from accounts.services.access_control_service import AccessControlService, PUBLIC_BAN_REASON
from common.exceptions import APIError

User = get_user_model()


@override_settings(
    OTP_WHITELIST_PHONES=["13800138000"],
    OTP_FIXED_WHITELIST_CODE="989898",
    ALIYUN_SMS_OTP_TEMPLATE_CODE="",
    ALIYUN_SMS_ACCOUNT_BANNED_TEMPLATE_CODE="SMS_511660153",
    DEVICE_ACCOUNT_LOGIN_ENABLED=True,
)
class AccessDenyLoginBlockTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="blocked_user", email="blocked@example.com", password="pass1234")
        AccessDenyEntry.objects.create(
            dimension=AccessDenyEntry.Dimension.USER_ID,
            dimension_value=str(self.user.id),
            related_user_id=self.user.id,
            reason_note="test ban",
        )

    def test_password_login_blocked_with_public_reason(self):
        response = self.client.post(
            "/api/v1/auth/password/login/",
            {
                "identifier": "blocked@example.com",
                "password": "pass1234",
                "bundle_id": "cn.Zhaodk.Health",
                "device_id": "device-block-test-001",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        payload = response.data
        self.assertEqual(payload.get("code"), 40371)
        self.assertEqual(payload.get("data", {}).get("public_reason"), PUBLIC_BAN_REASON)

    def test_email_otp_request_blocked(self):
        response = self.client.post(
            "/api/v1/otp/email/request/",
            {
                "email": "blocked@example.com",
                "bundle_id": "cn.Zhaodk.Health",
                "device_id": "device-block-test-002",
                "scene": "login",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data.get("code"), 40371)

    def test_phone_otp_request_blocked(self):
        phone = "+8613800138000"
        AccessDenyEntry.objects.create(
            dimension=AccessDenyEntry.Dimension.PHONE,
            dimension_value=phone,
        )
        response = self.client.post(
            "/api/v1/otp/phone/request/",
            {
                "phone_number": phone,
                "bundle_id": "cn.Zhaodk.Health",
                "device_id": "device-block-test-003",
                "scene": "login",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data.get("code"), 40371)


@override_settings(
    ALIYUN_SMS_ACCOUNT_BANNED_TEMPLATE_CODE="SMS_511660153",
)
class AccessControlServiceBanTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ban_target",
            email="ban@example.com",
            password="pass1234",
            is_active=True,
        )
        SocialIdentity.objects.create(
            user=self.user,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid="+8613900139000",
            bundle_id="cn.Zhaodk.Health",
        )
        SocialIdentity.objects.create(
            user=self.user,
            provider=SocialIdentity.Provider.EMAIL,
            provider_uid="ban@example.com",
            bundle_id="cn.Zhaodk.Health",
        )

    @patch("accounts.infrastructure.sms_provider.AliyunSMSProvider.send_account_banned")
    def test_ban_user_disables_without_expanding_identities(self, mock_send):
        mock_send.return_value = type(
            "R",
            (),
            {"accepted": True, "reason": "", "biz_id": "biz-1", "request_id": "req-1", "code": "OK", "status": "accepted", "unknown": False, "payload": {}},
        )()
        result = AccessControlService.ban_user(user=self.user, reason_note="违规", created_by_id=1, request_id="req-ban")
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(
            AccessDenyEntry.objects.filter(
                dimension=AccessDenyEntry.Dimension.USER_ID,
                dimension_value=str(self.user.id),
                revoked_at__isnull=True,
            ).exists()
        )
        self.assertFalse(
            AccessDenyEntry.objects.filter(
                dimension=AccessDenyEntry.Dimension.EMAIL,
                dimension_value="ban@example.com",
                revoked_at__isnull=True,
            ).exists()
        )
        self.assertFalse(
            AccessDenyEntry.objects.filter(
                dimension=AccessDenyEntry.Dimension.PHONE,
                dimension_value="+8613900139000",
                revoked_at__isnull=True,
            ).exists()
        )
        mock_send.assert_called_once()
        self.assertEqual(result["sms_status"], "sent")

    @patch("accounts.infrastructure.sms_provider.AliyunSMSProvider.send_account_banned")
    def test_ban_phone_with_user_only_creates_user_entry(self, mock_send):
        mock_send.return_value = type(
            "R",
            (),
            {"accepted": True, "reason": "", "biz_id": "biz-2", "request_id": "req-2", "code": "OK", "status": "accepted", "unknown": False, "payload": {}},
        )()
        result = AccessControlService.ban_phone(phone_number="13900139000", request_id="req-phone-ban")
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(result["matched_user"])
        self.assertTrue(
            AccessDenyEntry.objects.filter(
                dimension=AccessDenyEntry.Dimension.USER_ID,
                dimension_value=str(self.user.id),
                revoked_at__isnull=True,
            ).exists()
        )
        self.assertFalse(
            AccessDenyEntry.objects.filter(
                dimension=AccessDenyEntry.Dimension.PHONE,
                dimension_value="+8613900139000",
                revoked_at__isnull=True,
            ).exists()
        )

    @patch("accounts.infrastructure.sms_provider.AliyunSMSProvider.send_account_banned")
    def test_ban_phone_without_user_creates_phone_entry(self, mock_send):
        mock_send.return_value = type(
            "R",
            (),
            {"accepted": True, "reason": "", "biz_id": "biz-3", "request_id": "req-3", "code": "OK", "status": "accepted", "unknown": False, "payload": {}},
        )()
        result = AccessControlService.ban_phone(phone_number="13700137000", request_id="req-phone-only")
        self.assertFalse(result["matched_user"])
        self.assertTrue(
            AccessDenyEntry.objects.filter(
                dimension=AccessDenyEntry.Dimension.PHONE,
                dimension_value="+8613700137000",
                revoked_at__isnull=True,
            ).exists()
        )

    def test_check_raises_for_banned_email(self):
        AccessDenyEntry.objects.create(
            dimension=AccessDenyEntry.Dimension.EMAIL,
            dimension_value="blocked-email@example.com",
        )
        with self.assertRaises(APIError) as ctx:
            AccessControlService.check(email="blocked-email@example.com")
        self.assertEqual(ctx.exception.code, 40371)

    def test_revoke_user_entry_reactivates_user(self):
        entry = AccessDenyEntry.objects.create(
            dimension=AccessDenyEntry.Dimension.USER_ID,
            dimension_value=str(self.user.id),
            related_user_id=self.user.id,
        )
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        AccessControlService.revoke_entry(entry_id=entry.id, revoked_by_id=99)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
