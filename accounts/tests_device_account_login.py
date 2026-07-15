from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from unittest.mock import patch

from accounts.models import AccountDeviceSession, DeviceLoginCredential, SocialIdentity
from accounts.services.account_login_resolution_service import AccountLoginResolutionService
from accounts.services.device_login_service import DeviceLoginService
from common.exceptions import APIError

User = get_user_model()


@override_settings(
    DEVICE_ACCOUNT_LOGIN_ENABLED=True,
    DEVICE_ACCOUNT_LOGIN_ALLOWED_BUNDLES=[],
    ACCOUNT_IDENTITY_SCOPE_ALIASES={
        "cn.Zhaodk.Health": "cn.Zhaodk.Health",
        "cn.Zhaodk.MedicineBox": "cn.Zhaodk.Health",
    },
)
class DeviceAccountLoginTests(TestCase):
    bundle_id = "cn.Zhaodk.Health"
    device_id = "installation-device-001"
    device_secret = "high-entropy-device-secret-value-001"

    @patch("accounts.otp.views.OTPService.verify_phone_otp_and_issue_tokens")
    def test_phone_verify_view_forwards_device_secret(self, verify_mock):
        verify_mock.return_value = {"user_id": 1, "otp_id": "otp-test"}
        response = APIClient().post(
            "/api/v1/otp/phone/verify/",
            {
                "bundle_id": self.bundle_id,
                "device_id": self.device_id,
                "device_secret": self.device_secret,
                "phone_number": "+8615385056024",
                "otp_id": "otp-test",
                "code": "989898",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            verify_mock.call_args.kwargs["device_secret"], self.device_secret
        )

    def test_first_device_login_creates_user_and_identity(self):
        result = DeviceLoginService.authenticate_and_issue_tokens(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-device-1",
        )
        self.assertTrue(result["is_new_user"])
        self.assertTrue(result["is_device_account"])
        self.assertEqual(result["account_resolution"], "device_account_created")
        self.assertEqual(result["sign_in_method"], "device")
        self.assertIn("access_token", result)
        self.assertEqual(
            SocialIdentity.objects.filter(
                provider=SocialIdentity.Provider.DEVICE,
                provider_uid=self.device_id,
            ).count(),
            1,
        )
        self.assertEqual(
            DeviceLoginCredential.objects.filter(device_id=self.device_id).count(),
            1,
        )
        user = User.objects.get(id=result["user_id"])
        self.assertEqual(user.first_name, "device_04458cbcb12d")
        self.assertTrue(user.username.startswith("device_04458cbcb12d_"))

    def test_device_display_name_adds_suffix_when_base_name_exists(self):
        User.objects.create_user(
            username="existing-device-account",
            first_name="device_04458cbcb12d",
        )
        result = DeviceLoginService.authenticate_and_issue_tokens(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-device-display-name-1",
        )
        user = User.objects.get(id=result["user_id"])
        self.assertEqual(user.first_name, "device_04458cbcb12d_2")
        self.assertEqual(result["display_name"], "device_04458cbcb12d_2")

    def test_repeat_device_login_returns_same_user(self):
        first = DeviceLoginService.authenticate_and_issue_tokens(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-device-2a",
        )
        second = DeviceLoginService.authenticate_and_issue_tokens(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-device-2b",
        )
        self.assertEqual(first["user_id"], second["user_id"])
        self.assertFalse(second["is_new_user"])
        self.assertEqual(second["account_resolution"], "device_account_login")
        self.assertEqual(User.objects.count(), 1)

    def test_medicinebox_shares_identity_scope(self):
        first = DeviceLoginService.authenticate_and_issue_tokens(
            bundle_id="cn.Zhaodk.Health",
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-scope-a",
        )
        second = DeviceLoginService.authenticate_and_issue_tokens(
            bundle_id="cn.Zhaodk.MedicineBox",
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-scope-b",
        )
        self.assertEqual(first["user_id"], second["user_id"])
        self.assertEqual(second["identity_scope"], "cn.Zhaodk.Health")

    def test_invalid_secret_rejected(self):
        DeviceLoginService.authenticate_and_issue_tokens(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-secret-ok",
        )
        with self.assertRaises(APIError) as ctx:
            DeviceLoginService.authenticate_and_issue_tokens(
                bundle_id=self.bundle_id,
                device_id=self.device_id,
                device_secret="wrong-secret",
                request_id="req-secret-bad",
            )
        self.assertEqual(ctx.exception.code, 40161)
        cred = DeviceLoginCredential.objects.get(device_id=self.device_id)
        self.assertEqual(cred.failed_attempts, 1)

    def test_upgrade_then_guest_creates_new_device_account(self):
        device_result = DeviceLoginService.authenticate_and_issue_tokens(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-upgrade-1",
        )
        u1_id = device_result["user_id"]

        def _create_phone_user():
            user = User.objects.create(username="phone_upgrade_u1", email="", is_active=True)
            user.set_unusable_password()
            user.save(update_fields=["password"])
            return user

        upgraded = AccountLoginResolutionService.resolve_verified_identity(
            provider=SocialIdentity.Provider.PHONE,
            normalized_provider_uid="+8613800000001",
            real_bundle_id=self.bundle_id,
            identity_scope="cn.Zhaodk.Health",
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-upgrade-2",
            create_user=_create_phone_user,
        )
        self.assertEqual(upgraded["user_id"], u1_id)
        self.assertEqual(upgraded["account_resolution"], "device_account_upgraded")
        self.assertFalse(upgraded["is_device_account"])
        self.assertFalse(
            SocialIdentity.objects.filter(
                provider=SocialIdentity.Provider.DEVICE,
                provider_uid=self.device_id,
            ).exists()
        )
        self.assertTrue(
            DeviceLoginCredential.objects.filter(device_id=self.device_id).exists()
        )
        self.assertTrue(
            AccountDeviceSession.objects.filter(
                user_id=u1_id,
                status=AccountDeviceSession.Status.ACTIVE,
            ).exists()
        )
        self.assertTrue(
            AccountDeviceSession.objects.filter(
                user_id=u1_id,
                status=AccountDeviceSession.Status.REVOKED,
                revoked_reason="device_account_upgraded",
            ).exists()
        )

        guest_again = DeviceLoginService.authenticate_and_issue_tokens(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-upgrade-3",
        )
        self.assertNotEqual(guest_again["user_id"], u1_id)
        self.assertEqual(guest_again["account_resolution"], "device_account_created")
        self.assertTrue(guest_again["is_device_account"])

    def test_existing_formal_identity_keeps_device_identity(self):
        device_result = DeviceLoginService.authenticate_and_issue_tokens(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-switch-1",
        )
        u1_id = device_result["user_id"]

        u2 = User.objects.create(username="phone_u2", email="", is_active=True)
        u2.set_unusable_password()
        u2.save(update_fields=["password"])
        SocialIdentity.objects.create(
            user=u2,
            bundle_id="cn.Zhaodk.Health",
            provider=SocialIdentity.Provider.PHONE,
            provider_uid="+8613800000002",
        )

        switched = AccountLoginResolutionService.resolve_verified_identity(
            provider=SocialIdentity.Provider.PHONE,
            normalized_provider_uid="+8613800000002",
            real_bundle_id=self.bundle_id,
            identity_scope="cn.Zhaodk.Health",
            device_id=self.device_id,
            request_id="req-switch-2",
            create_user=lambda: User.objects.create(username="should_not_run"),
        )
        self.assertEqual(switched["user_id"], u2.id)
        self.assertEqual(switched["account_resolution"], "existing_identity_login")
        self.assertTrue(
            SocialIdentity.objects.filter(
                user_id=u1_id,
                provider=SocialIdentity.Provider.DEVICE,
                provider_uid=self.device_id,
            ).exists()
        )

        back = DeviceLoginService.authenticate_and_issue_tokens(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-switch-3",
        )
        self.assertEqual(back["user_id"], u1_id)

    def test_formal_login_without_device_secret_does_not_upgrade_device_account(self):
        device_result = DeviceLoginService.authenticate_and_issue_tokens(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-secret-required-1",
        )

        def _create_formal_user():
            user = User.objects.create(username="formal-without-device-secret")
            user.set_unusable_password()
            user.save(update_fields=["password"])
            return user

        result = AccountLoginResolutionService.resolve_verified_identity(
            provider=SocialIdentity.Provider.PHONE,
            normalized_provider_uid="+8613800000011",
            real_bundle_id=self.bundle_id,
            identity_scope="cn.Zhaodk.Health",
            device_id=self.device_id,
            device_secret="",
            request_id="req-secret-required-2",
            create_user=_create_formal_user,
        )
        self.assertNotEqual(result["user_id"], device_result["user_id"])
        self.assertEqual(result["account_resolution"], "formal_account_created")
        self.assertTrue(
            SocialIdentity.objects.filter(
                user_id=device_result["user_id"],
                provider=SocialIdentity.Provider.DEVICE,
                provider_uid=self.device_id,
            ).exists()
        )

    def test_formal_login_with_wrong_device_secret_is_rejected(self):
        DeviceLoginService.authenticate_and_issue_tokens(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            device_secret=self.device_secret,
            request_id="req-secret-invalid-1",
        )

        with self.assertRaises(APIError) as ctx:
            AccountLoginResolutionService.resolve_verified_identity(
                provider=SocialIdentity.Provider.EMAIL,
                normalized_provider_uid="security@example.com",
                real_bundle_id=self.bundle_id,
                identity_scope="cn.Zhaodk.Health",
                device_id=self.device_id,
                device_secret="wrong-device-secret",
                request_id="req-secret-invalid-2",
                create_user=lambda: User.objects.create(username="must-not-create"),
            )
        self.assertEqual(ctx.exception.code, 40161)
        self.assertFalse(
            SocialIdentity.objects.filter(
                provider=SocialIdentity.Provider.EMAIL,
                provider_uid="security@example.com",
            ).exists()
        )
