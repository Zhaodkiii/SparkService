from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, override_settings
from unittest.mock import patch
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import AccountDeviceSession, TrustedDevice
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


@override_settings(
    OTP_WHITELIST_PHONES=["13800138000"],
    OTP_FIXED_WHITELIST_CODE="989898",
    ALIYUN_SMS_OTP_TEMPLATE_CODE="",
)
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

        old_device = TrustedDevice.objects.get(
            bundle_id=self.bundle_a,
            device_id=self.device_a1,
            user=user,
        )
        new_device = TrustedDevice.objects.get(
            bundle_id=self.bundle_a,
            device_id=self.device_a2,
            user=user,
        )
        self.assertTrue(old_device.is_revoked)
        self.assertFalse(new_device.is_revoked)

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

    def test_same_install_login_revokes_other_user_device_and_session(self):
        User = get_user_model()
        user_a = User.objects.create_user(username="install_user_a", password="x")
        user_b = User.objects.create_user(username="install_user_b", password="x")
        shared_device = "shared-install-id"

        session_a = DeviceSessionService.activate_session_on_login(
            user=user_a,
            bundle_id=self.bundle_a,
            device_id=shared_device,
            request_id="req-a",
        )
        self.assertEqual(session_a.status, AccountDeviceSession.Status.ACTIVE)
        device_a = TrustedDevice.objects.get(
            bundle_id=self.bundle_a,
            device_id=shared_device,
            user=user_a,
        )
        self.assertFalse(device_a.is_revoked)

        session_b = DeviceSessionService.activate_session_on_login(
            user=user_b,
            bundle_id=self.bundle_a,
            device_id=shared_device,
            request_id="req-b",
        )
        self.assertEqual(session_b.status, AccountDeviceSession.Status.ACTIVE)

        device_a.refresh_from_db()
        device_b = TrustedDevice.objects.get(
            bundle_id=self.bundle_a,
            device_id=shared_device,
            user=user_b,
        )
        self.assertTrue(device_a.is_revoked)
        self.assertFalse(device_b.is_revoked)

        session_a.refresh_from_db()
        self.assertEqual(session_a.status, AccountDeviceSession.Status.REVOKED)

    def test_profile_binding_failure_does_not_revoke_existing_install_user(self):
        User = get_user_model()
        user_a = User.objects.create_user(username="rollback_install_a", password="x")
        user_b = User.objects.create_user(username="rollback_install_b", password="x")
        shared_device = "rollback-shared-install"
        session_a = DeviceSessionService.activate_session_on_login(
            user=user_a,
            bundle_id=self.bundle_a,
            device_id=shared_device,
            request_id="req-a",
        )

        with patch(
            "accounts.services.device_service.DeviceService.ensure_user_device_profile_from_anonymous",
            side_effect=IntegrityError("broken device constraint"),
        ):
            with self.assertRaises(IntegrityError):
                DeviceSessionService.activate_session_on_login(
                    user=user_b,
                    bundle_id=self.bundle_a,
                    device_id=shared_device,
                    request_id="req-b",
                )

        session_a.refresh_from_db()
        session_a.trusted_device.refresh_from_db()
        self.assertEqual(session_a.status, AccountDeviceSession.Status.ACTIVE)
        self.assertFalse(session_a.trusted_device.is_revoked)
        self.assertFalse(
            TrustedDevice.objects.filter(
                bundle_id=self.bundle_a,
                device_id=shared_device,
                user=user_b,
            ).exists()
        )

    def test_logout_uses_token_session_id_when_provided(self):
        user = get_user_model().objects.create_user(username="logout_claims", password="x")
        bundle_id = self.bundle_a
        device_id = "logout-device"
        session = DeviceSessionService.activate_session_on_login(
            user=user,
            bundle_id=bundle_id,
            device_id=device_id,
            request_id="req-logout",
        )
        tokens = DeviceSessionService.issue_tokens_for_session(
            user=user,
            session=session,
            bundle_id=bundle_id,
            device_id=device_id,
        )
        access = AccessToken(tokens["access_token"])
        claims = DeviceSessionService._claims_from_validated_token(access)

        DeviceSessionService.logout_current_session(user=user, claims=claims, request_id="req-logout")

        session.refresh_from_db()
        self.assertEqual(session.status, AccountDeviceSession.Status.LOGGED_OUT)
        session.trusted_device.refresh_from_db()
        self.assertTrue(session.trusted_device.is_revoked)


class DeviceRegisterViewAuthTests(TestCase):
    bundle_id = "com.sparkclient.ios"
    register_url = "/api/v1/device/register/"

    def _payload(self, *, device_id: str) -> dict:
        return {
            "device_id": device_id,
            "bundle_id": self.bundle_id,
            "platform": "iOS",
        }

    def test_anonymous_register_without_authorization_succeeds(self):
        client = APIClient()
        response = client.post(self.register_url, self._payload(device_id="anon-device"), format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)
        self.assertTrue(
            TrustedDevice.objects.filter(
                bundle_id=self.bundle_id,
                device_id="anon-device",
                user__isnull=True,
            ).exists()
        )

    def test_invalid_authorization_returns_401_without_anonymous_row(self):
        client = APIClient()
        response = client.post(
            self.register_url,
            self._payload(device_id="bad-auth-device"),
            format="json",
            HTTP_AUTHORIZATION="Bearer not-a-real-jwt",
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(
            TrustedDevice.objects.filter(bundle_id=self.bundle_id, device_id="bad-auth-device").exists()
        )

    def _login_phone(self, *, device_id: str) -> dict:
        requested = OTPService.request_phone_otp(
            phone_number="13800138000",
            provider_uid="",
            bundle_id=self.bundle_id,
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
            bundle_id=self.bundle_id,
            device_id=device_id,
        )

    @override_settings(
        OTP_WHITELIST_PHONES=["13800138000"],
        OTP_FIXED_WHITELIST_CODE="989898",
        ALIYUN_SMS_OTP_TEMPLATE_CODE="",
    )
    def test_old_device_authenticated_register_returns_401(self):
        first = self._login_phone(device_id="device-a1")
        second = self._login_phone(device_id="device-a2")

        client = APIClient()
        response = client.post(
            self.register_url,
            self._payload(device_id="device-a1"),
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {first['access_token']}",
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn(
            response.json()["msg"],
            ("device_session_replaced", "device_session_revoked", "device_session_not_found"),
        )

        active_row = TrustedDevice.objects.get(
            bundle_id=self.bundle_id,
            device_id="device-a2",
            user_id=first["user_id"],
        )
        self.assertEqual(active_row.push_token, "")

        client.credentials(HTTP_AUTHORIZATION=f"Bearer {second['access_token']}")
        ok = client.post(self.register_url, self._payload(device_id="device-a2"), format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["code"], 0)

    @override_settings(
        OTP_WHITELIST_PHONES=["13800138000"],
        OTP_FIXED_WHITELIST_CODE="989898",
        ALIYUN_SMS_OTP_TEMPLATE_CODE="",
    )
    def test_authenticated_register_rejected_when_trusted_device_revoked(self):
        tokens = self._login_phone(device_id="revoked-reg-device")
        user = get_user_model().objects.get(id=tokens["user_id"])
        active = AccountDeviceSession.objects.get(
            user=user,
            status=AccountDeviceSession.Status.ACTIVE,
        )
        TrustedDevice.objects.filter(pk=active.trusted_device_id).update(is_revoked=True)

        client = APIClient()
        response = client.post(
            self.register_url,
            self._payload(device_id="revoked-reg-device"),
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["msg"], "device_session_revoked")
