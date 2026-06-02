from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import AccountDeviceSession
from accounts.services.device_session_service import DeviceSessionService
from accounts.services.otp_service import OTPService
from common.exceptions import APIError


@override_settings(
    OTP_WHITELIST_PHONES=["13800138000"],
    OTP_FIXED_WHITELIST_CODE="989898",
    ALIYUN_SMS_OTP_TEMPLATE_CODE="",
)
class DeviceSessionClaimsExtractionTests(TestCase):
    def test_claims_from_access_token_object(self):
        user = get_user_model().objects.create_user(username="claims_test", password="x")
        token = AccessToken.for_user(user)
        token["device_session_id"] = 99
        claims = DeviceSessionService._claims_from_validated_token(token)
        self.assertEqual(claims["device_session_id"], 99)
        self.assertEqual(int(claims["user_id"]), user.id)

    def test_admin_token_skips_device_session_validation(self):
        user = get_user_model().objects.create_user(username="admin_claims_test", password="x")
        token = AccessToken.for_user(user)
        claims = DeviceSessionService._claims_from_validated_token(token)
        self.assertFalse(DeviceSessionService.claims_require_device_session(claims))
        DeviceSessionService.validate_access_claims(user=user, validated_token=token)


class DeviceSessionServiceTests(TestCase):
    bundle_a = "com.sparkclient.ios"
    device_a1 = "device-a1"
    device_a2 = "device-a2"

    def _login_phone(self, *, device_id: str) -> dict:
        requested = OTPService.request_phone_otp(
            phone_number="13800138000",
            provider_uid="",
            bundle_id=self.bundle_a,
            device_id=device_id,
            ip_address="127.0.0.1",
            request_id=f"req-{device_id}",
        )
        return OTPService.verify_phone_otp_and_issue_tokens(
            otp_id=requested["otp_id"],
            phone_number="13800138000",
            code="989898",
            request_id=f"req-{device_id}",
            ip_address="127.0.0.1",
            user_agent="unit-test",
            bundle_id=self.bundle_a,
            device_id=device_id,
        )

    def test_second_device_login_revokes_first_session(self):
        first = self._login_phone(device_id=self.device_a1)
        second = self._login_phone(device_id=self.device_a2)

        user = get_user_model().objects.get(id=first["user_id"])
        self.assertEqual(first["user_id"], second["user_id"])

        active = AccountDeviceSession.objects.filter(
            user=user,
            status=AccountDeviceSession.Status.ACTIVE,
        )
        self.assertEqual(active.count(), 1)
        self.assertEqual(active.first().device_id, self.device_a2)

        revoked = AccountDeviceSession.objects.filter(
            user=user,
            status=AccountDeviceSession.Status.REVOKED,
            device_id=self.device_a1,
        )
        self.assertEqual(revoked.count(), 1)

    def test_old_device_refresh_rejected_after_replacement(self):
        first = self._login_phone(device_id=self.device_a1)
        self._login_phone(device_id=self.device_a2)

        with self.assertRaises(APIError) as ctx:
            DeviceSessionService.validate_refresh_request(
                refresh_token_str=first["refresh_token"],
                bundle_id=self.bundle_a,
                device_id=self.device_a1,
            )
        self.assertIn(
            ctx.exception.msg,
            ("device_session_revoked", "device_session_replaced", "token_not_valid"),
        )

    def test_active_device_refresh_succeeds(self):
        tokens = self._login_phone(device_id=self.device_a1)
        user = get_user_model().objects.get(id=tokens["user_id"])
        _user, session, _claims = DeviceSessionService.validate_refresh_request(
            refresh_token_str=tokens["refresh_token"],
            bundle_id=self.bundle_a,
            device_id=self.device_a1,
        )
        rotated = DeviceSessionService.rotate_tokens_after_refresh(
            user=user,
            session=session,
            old_refresh_str=tokens["refresh_token"],
            bundle_id=self.bundle_a,
            device_id=self.device_a1,
        )
        self.assertTrue(rotated["access_token"])
        self.assertTrue(rotated["refresh_token"])

    def test_device_mismatch_on_refresh(self):
        tokens = self._login_phone(device_id=self.device_a1)
        with self.assertRaises(APIError) as ctx:
            DeviceSessionService.validate_refresh_request(
                refresh_token_str=tokens["refresh_token"],
                bundle_id=self.bundle_a,
                device_id=self.device_a2,
            )
        self.assertEqual(ctx.exception.msg, "device_mismatch")
