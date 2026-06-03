from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import TrustedDevice
from accounts.services.device_service import DeviceService


class DeviceServicePushTokenTests(TestCase):
    def setUp(self):
        self.device = TrustedDevice.objects.create(
            bundle_id="com.spark.test",
            device_id="device-push-token",
            push_token="existing-token",
            notifications_enabled=True,
        )

    def test_null_push_token_does_not_clear_existing(self):
        DeviceService.register_device(
            user=None,
            data={
                "device_id": self.device.device_id,
                "bundle_id": self.device.bundle_id,
                "push_token": None,
                "notifications_enabled": True,
            },
            explicit_keys={"device_id", "bundle_id", "push_token", "notifications_enabled"},
            request_id="req-null-token",
        )
        self.device.refresh_from_db()
        self.assertEqual(self.device.push_token, "existing-token")
        self.assertTrue(self.device.notifications_enabled)

    def test_empty_push_token_clears_existing(self):
        DeviceService.register_device(
            user=None,
            data={
                "device_id": self.device.device_id,
                "bundle_id": self.device.bundle_id,
                "push_token": "",
                "notifications_enabled": False,
            },
            explicit_keys={"device_id", "bundle_id", "push_token", "notifications_enabled"},
            request_id="req-clear-token",
        )
        self.device.refresh_from_db()
        self.assertEqual(self.device.push_token, "")
        self.assertFalse(self.device.notifications_enabled)

    def test_omitted_push_token_leaves_existing_unchanged(self):
        DeviceService.register_device(
            user=None,
            data={
                "device_id": self.device.device_id,
                "bundle_id": self.device.bundle_id,
                "notifications_enabled": True,
            },
            explicit_keys={"device_id", "bundle_id", "notifications_enabled"},
            request_id="req-omit-token",
        )
        self.device.refresh_from_db()
        self.assertEqual(self.device.push_token, "existing-token")


class DeviceServiceUserIsolationTests(TestCase):
    bundle_id = "com.spark.test"
    device_id = "shared-install-id"

    def setUp(self):
        User = get_user_model()
        self.user1 = User.objects.create_user(username="user1", password="x")
        self.user2 = User.objects.create_user(username="user2", password="x")
        self.anon = TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=None,
            push_token="anon-token",
            country_code="CN",
        )
        self.user1_device = TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=self.user1,
            push_token="user1-token",
            country_code="US",
        )

    def _register(self, *, user, push_token: str, country_code: str):
        DeviceService.register_device(
            user=user,
            data={
                "device_id": self.device_id,
                "bundle_id": self.bundle_id,
                "push_token": push_token,
                "notifications_enabled": True,
                "country_code": country_code,
            },
            explicit_keys={
                "device_id",
                "bundle_id",
                "push_token",
                "notifications_enabled",
                "country_code",
            },
            request_id="req-isolation",
        )

    def test_same_install_can_have_anonymous_and_user_rows(self):
        self.assertEqual(
            TrustedDevice.objects.filter(bundle_id=self.bundle_id, device_id=self.device_id).count(),
            2,
        )

    def test_user2_register_does_not_overwrite_user1(self):
        self._register(user=self.user2, push_token="user2-token", country_code="HK")
        self.user1_device.refresh_from_db()
        self.anon.refresh_from_db()
        self.assertEqual(self.user1_device.push_token, "user1-token")
        self.assertEqual(self.user1_device.country_code, "US")
        self.assertEqual(self.anon.push_token, "anon-token")

        user2_row = TrustedDevice.objects.get(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=self.user2,
        )
        self.assertEqual(user2_row.push_token, "user2-token")
        self.assertEqual(user2_row.country_code, "HK")

    def test_anonymous_register_does_not_touch_user_rows(self):
        DeviceService.register_device(
            user=None,
            data={
                "device_id": self.device_id,
                "bundle_id": self.bundle_id,
                "push_token": "anon-updated",
                "country_code": "JP",
            },
            explicit_keys={"device_id", "bundle_id", "push_token", "country_code"},
            request_id="req-anon",
        )
        self.user1_device.refresh_from_db()
        self.anon.refresh_from_db()
        self.assertEqual(self.anon.push_token, "anon-updated")
        self.assertEqual(self.anon.country_code, "JP")
        self.assertEqual(self.user1_device.push_token, "user1-token")


class DeviceServiceAnonymousMergeTests(TestCase):
    bundle_id = "com.spark.test"
    device_id = "partial-merge-install"

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="merge_user", password="x")
        self.anon = TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=None,
            country_code="CN",
            app_version="1.0",
            push_token="anon-token",
            notifications_enabled=True,
        )

    def test_authenticated_register_partial_body_preserves_anonymous_profile(self):
        DeviceService.register_device(
            user=self.user,
            data={
                "device_id": self.device_id,
                "bundle_id": self.bundle_id,
            },
            explicit_keys={"device_id", "bundle_id"},
            request_id="req-partial",
        )

        user_row = TrustedDevice.objects.get(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=self.user,
        )
        self.anon.refresh_from_db()

        self.assertEqual(user_row.country_code, "CN")
        self.assertEqual(user_row.app_version, "1.0")
        self.assertEqual(user_row.push_token, "anon-token")
        self.assertTrue(user_row.notifications_enabled)
        self.assertIsNone(self.anon.user_id)
        self.assertEqual(self.anon.country_code, "CN")
        self.assertEqual(self.anon.app_version, "1.0")
        self.assertEqual(self.anon.push_token, "anon-token")

    def test_explicit_empty_app_version_does_not_clear_anonymous_merge(self):
        TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=self.user,
            app_version="1.0",
            country_code="CN",
        )
        DeviceService.register_device(
            user=self.user,
            data={
                "device_id": self.device_id,
                "bundle_id": self.bundle_id,
                "app_version": "",
            },
            explicit_keys={"device_id", "bundle_id", "app_version"},
            request_id="req-empty-version",
        )
        user_row = TrustedDevice.objects.get(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=self.user,
        )
        self.assertEqual(user_row.app_version, "1.0")


class DeviceLinkingServiceTests(TestCase):
    bundle_id = "com.spark.test"
    device_id = "link-install"

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="link_user", password="x")
        self.anon = TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=None,
            country_code="CN",
            push_token="anon-token",
            notifications_enabled=True,
        )

    def test_login_linking_creates_user_row_without_rebinding_anonymous(self):
        from accounts.services.device_linking_service import DeviceLinkingService

        DeviceLinkingService.try_attach_user_to_trusted_device(
            user=self.user,
            device_id=self.device_id,
            bundle_id=self.bundle_id,
            request_id="req-link",
        )

        self.anon.refresh_from_db()
        self.assertIsNone(self.anon.user_id)
        self.assertEqual(self.anon.push_token, "anon-token")

        user_row = TrustedDevice.objects.get(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=self.user,
        )
        self.assertEqual(user_row.country_code, "CN")
        self.assertEqual(user_row.push_token, "anon-token")
        self.assertTrue(user_row.notifications_enabled)
