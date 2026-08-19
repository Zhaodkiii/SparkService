from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient
from unittest.mock import patch

from accounts.models import AccessDenyEntry, AccessDenyHit, PhoneOTP, SocialIdentity, TrustedDevice
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


@override_settings(
    OTP_WHITELIST_PHONES=["13800138000", "13700137001"],
    OTP_FIXED_WHITELIST_CODE="989898",
    ALIYUN_SMS_OTP_TEMPLATE_CODE="",
    ALIYUN_SMS_ACCOUNT_BANNED_TEMPLATE_CODE="SMS_511660153",
    DEVICE_ACCOUNT_LOGIN_ENABLED=True,
)
class AccessDenyDeviceRegistrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.bundle_id = "cn.Zhaodk.Health"
        self.blocked_device_id = "blocked-device-reg-001"
        AccessDenyEntry.objects.create(
            dimension=AccessDenyEntry.Dimension.DEVICE,
            dimension_value=self.blocked_device_id,
            reason_note="device blocked",
        )

    def test_device_login_registration_blocked_on_blocked_device(self):
        response = self.client.post(
            "/api/v1/auth/device/login/",
            {
                "bundle_id": self.bundle_id,
                "device_id": self.blocked_device_id,
                "device_secret": "secret12345678",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data.get("code"), 40371)

    def test_phone_otp_request_blocked_on_blocked_device_unregistered_phone(self):
        request_resp = self.client.post(
            "/api/v1/otp/phone/request/",
            {
                "phone_number": "13700137001",
                "bundle_id": self.bundle_id,
                "device_id": self.blocked_device_id,
                "scene": "login",
            },
            format="json",
        )
        self.assertEqual(request_resp.status_code, 403)
        self.assertEqual(request_resp.data.get("code"), 40371)
        self.assertFalse(
            PhoneOTP.objects.filter(phone_number="+8613700137001").exists()
        )

    def test_phone_otp_request_blocked_on_blocked_device_registered_phone(self):
        registered = User.objects.create_user(
            username="registered_on_blocked_device",
            email="registered-device@example.com",
            password="pass1234",
            is_active=True,
        )
        SocialIdentity.objects.create(
            user=registered,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid="+8613800138000",
            bundle_id="cn.Zhaodk.Health",
        )
        request_resp = self.client.post(
            "/api/v1/otp/phone/request/",
            {
                "phone_number": "13800138000",
                "bundle_id": self.bundle_id,
                "device_id": self.blocked_device_id,
                "scene": "login",
            },
            format="json",
        )
        self.assertEqual(request_resp.status_code, 403)
        self.assertEqual(request_resp.data.get("code"), 40371)
        self.assertFalse(
            PhoneOTP.objects.filter(phone_number="+8613800138000").exists()
        )

    def test_existing_user_can_login_on_blocked_device(self):
        allowed_user = User.objects.create_user(
            username="allowed_on_blocked_device",
            email="allowed-device@example.com",
            password="pass1234",
            is_active=True,
        )
        response = self.client.post(
            "/api/v1/auth/password/login/",
            {
                "identifier": "allowed-device@example.com",
                "password": "pass1234",
                "bundle_id": self.bundle_id,
                "device_id": self.blocked_device_id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("access", response.data.get("data", {}))


@override_settings(
    ALIYUN_SMS_ACCOUNT_BANNED_TEMPLATE_CODE="SMS_511660153",
    DEVICE_ACCOUNT_LOGIN_ENABLED=True,
)
class AccessDenyDeviceExpansionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="device_expand_target",
            email="device-expand@example.com",
            password="pass1234",
            is_active=True,
        )
        TrustedDevice.objects.create(
            user=self.user,
            bundle_id="cn.Zhaodk.Health",
            device_id="trusted-device-expand-001",
        )

    @patch("accounts.infrastructure.sms_provider.AliyunSMSProvider.send_account_banned")
    def test_ban_user_expands_related_devices(self, mock_send):
        mock_send.return_value = type(
            "R",
            (),
            {"accepted": False, "reason": "skipped", "biz_id": "", "request_id": "", "code": "", "status": "skipped", "unknown": False, "payload": {}},
        )()
        AccessControlService.ban_user(user=self.user, reason_note="违规", created_by_id=1, request_id="req-device-expand")
        self.assertTrue(
            AccessDenyEntry.objects.filter(
                dimension=AccessDenyEntry.Dimension.DEVICE,
                dimension_value="trusted-device-expand-001",
                source=AccessDenyEntry.Source.AUTO_EXPAND,
                related_user_id=self.user.id,
                revoked_at__isnull=True,
            ).exists()
        )

    def test_check_device_registration_raises_for_blocked_device(self):
        AccessDenyEntry.objects.create(
            dimension=AccessDenyEntry.Dimension.DEVICE,
            dimension_value="manual-device-block-001",
        )
        with self.assertRaises(APIError) as ctx:
            AccessControlService.check_device_registration(device_id="manual-device-block-001")
        self.assertEqual(ctx.exception.code, 40371)


@override_settings(
    OTP_WHITELIST_PHONES=["13800138000"],
    OTP_FIXED_WHITELIST_CODE="989898",
    ALIYUN_SMS_OTP_TEMPLATE_CODE="",
    ALIYUN_SMS_ACCOUNT_BANNED_TEMPLATE_CODE="SMS_511660153",
    DEVICE_ACCOUNT_LOGIN_ENABLED=True,
)
class AccessDenyHitRecordTests(TransactionTestCase):
    def setUp(self):
        AccessDenyHit.objects.all().delete()
        self.client = APIClient()
        self.bundle_id = "cn.Zhaodk.Health"
        self.user = User.objects.create_user(
            username="hit_blocked_user",
            email="hit-blocked@example.com",
            password="pass1234",
        )
        self.entry = AccessDenyEntry.objects.create(
            dimension=AccessDenyEntry.Dimension.USER_ID,
            dimension_value=str(self.user.id),
            related_user_id=self.user.id,
        )

    def test_password_login_records_single_hit(self):
        response = self.client.post(
            "/api/v1/auth/password/login/",
            {
                "identifier": "hit-blocked@example.com",
                "password": "pass1234",
                "bundle_id": self.bundle_id,
                "device_id": "hit-record-device-001",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        hits = AccessDenyHit.objects.all()
        self.assertEqual(hits.count(), 1)
        hit = hits.first()
        self.assertEqual(hit.action, AccessDenyHit.Action.LOGIN)
        self.assertEqual(hit.hit_dimension, AccessDenyEntry.Dimension.USER_ID)
        self.assertEqual(hit.hit_value, str(self.user.id))
        self.assertEqual(hit.deny_entry_id, self.entry.id)
        self.assertEqual(hit.device_id, "hit-record-device-001")

    def test_device_registration_records_single_hit(self):
        device_entry = AccessDenyEntry.objects.create(
            dimension=AccessDenyEntry.Dimension.DEVICE,
            dimension_value="hit-record-device-002",
        )
        response = self.client.post(
            "/api/v1/auth/device/login/",
            {
                "bundle_id": self.bundle_id,
                "device_id": "hit-record-device-002",
                "device_secret": "secret12345678",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        hits = AccessDenyHit.objects.filter(hit_dimension=AccessDenyEntry.Dimension.DEVICE)
        self.assertEqual(hits.count(), 1)
        hit = hits.first()
        self.assertEqual(hit.action, AccessDenyHit.Action.REGISTER)
        self.assertEqual(hit.hit_value, "hit-record-device-002")
        self.assertEqual(hit.deny_entry_id, device_entry.id)

    def test_email_otp_request_records_otp_request_hit(self):
        email_entry = AccessDenyEntry.objects.create(
            dimension=AccessDenyEntry.Dimension.EMAIL,
            dimension_value="hit-blocked@example.com",
        )
        response = self.client.post(
            "/api/v1/otp/email/request/",
            {
                "email": "hit-blocked@example.com",
                "bundle_id": self.bundle_id,
                "device_id": "hit-record-device-003",
                "scene": "login",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        hits = AccessDenyHit.objects.filter(action=AccessDenyHit.Action.OTP_REQUEST)
        self.assertEqual(hits.count(), 1)
        self.assertEqual(hits.first().deny_entry_id, email_entry.id)

    def test_hit_survives_outer_atomic_rollback(self):
        device_id = "durable-hit-device-001"
        AccessDenyEntry.objects.create(
            dimension=AccessDenyEntry.Dimension.DEVICE,
            dimension_value=device_id,
        )
        with transaction.atomic():
            with self.assertRaises(APIError) as ctx:
                AccessControlService.check_device_registration(device_id=device_id)
            self.assertEqual(ctx.exception.code, 40371)
        self.assertEqual(
            AccessDenyHit.objects.filter(
                hit_dimension=AccessDenyEntry.Dimension.DEVICE,
                hit_value=device_id,
                action=AccessDenyHit.Action.REGISTER,
            ).count(),
            1,
        )

    def test_phone_otp_request_records_hit_for_inactive_banned_user(self):
        phone = "+8613800138000"
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        SocialIdentity.objects.create(
            user=self.user,
            provider=SocialIdentity.Provider.PHONE,
            provider_uid=phone,
            bundle_id=self.bundle_id,
        )
        response = self.client.post(
            "/api/v1/otp/phone/request/",
            {
                "phone_number": phone,
                "bundle_id": self.bundle_id,
                "device_id": "durable-hit-device-otp-001",
                "scene": "login",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data.get("code"), 40371)
        self.assertEqual(
            AccessDenyHit.objects.filter(
                action=AccessDenyHit.Action.OTP_REQUEST,
                hit_dimension=AccessDenyEntry.Dimension.USER_ID,
                hit_value=str(self.user.id),
            ).count(),
            1,
        )
