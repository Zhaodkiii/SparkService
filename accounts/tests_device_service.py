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


class DeviceServiceUpgradeTests(TestCase):
    bundle_id = "com.spark.test"
    device_id = "upgrade-install"

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="upgrade_user", password="x")
        self.anon = TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=None,
            country_code="CN",
            app_version="1.0",
            push_token="anon-token",
        )

    def test_authenticated_register_upgrades_anonymous_row(self):
        anon_id = self.anon.id
        DeviceService.register_device(
            user=self.user,
            data={
                "device_id": self.device_id,
                "bundle_id": self.bundle_id,
                "country_code": "US",
            },
            explicit_keys={"device_id", "bundle_id", "country_code"},
            request_id="req-upgrade",
        )
        self.assertFalse(
            TrustedDevice.objects.filter(
                bundle_id=self.bundle_id,
                device_id=self.device_id,
                user__isnull=True,
            ).exists()
        )
        user_row = TrustedDevice.objects.get(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=self.user,
        )
        self.assertEqual(user_row.id, anon_id)
        self.assertEqual(user_row.country_code, "US")
        self.assertFalse(user_row.is_revoked)


class DeviceServiceRevokedReuseTests(TestCase):
    bundle_id = "com.spark.test"
    device_id = "revoked-reuse"

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="revoked_user", password="x")
        self.revoked_row = TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=self.user,
            is_revoked=True,
            country_code="CN",
            push_token="old-token",
        )

    def test_unsigned_register_updates_revoked_user_row_with_hint(self):
        DeviceService.register_device(
            user=None,
            data={
                "device_id": self.device_id,
                "bundle_id": self.bundle_id,
                "user_id": self.user.id,
                "push_token": "new-token",
            },
            explicit_keys={
                "device_id",
                "bundle_id",
                "user_id",
                "push_token",
            },
            request_id="req-revoked",
        )
        self.revoked_row.refresh_from_db()
        self.assertEqual(self.revoked_row.user_id, self.user.id)
        self.assertTrue(self.revoked_row.is_revoked)
        self.assertEqual(self.revoked_row.push_token, "new-token")
        self.assertFalse(
            TrustedDevice.objects.filter(
                bundle_id=self.bundle_id,
                device_id=self.device_id,
                user__isnull=True,
            ).exists()
        )

    def test_unsigned_cannot_create_arbitrary_user_row_from_hint(self):
        User = get_user_model()
        other = User.objects.create_user(username="other", password="x")
        DeviceService.register_device(
            user=None,
            data={
                "device_id": self.device_id,
                "bundle_id": self.bundle_id,
                "user_id": other.id,
            },
            explicit_keys={"device_id", "bundle_id", "user_id"},
            request_id="req-hint-miss",
        )
        self.assertFalse(TrustedDevice.objects.filter(user=other).exists())
        self.revoked_row.refresh_from_db()
        self.assertEqual(self.revoked_row.push_token, "old-token")


class DeviceServiceUserIsolationTests(TestCase):
    bundle_id = "com.spark.test"
    device_id = "shared-install-id"

    def setUp(self):
        User = get_user_model()
        self.user1 = User.objects.create_user(username="user1", password="x")
        self.user2 = User.objects.create_user(username="user2", password="x")
        self.user1_device = TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=self.user1,
            push_token="user1-token",
            country_code="US",
            is_revoked=True,
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

    def test_user2_register_creates_separate_row(self):
        self._register(user=self.user2, push_token="user2-token", country_code="HK")
        self.user1_device.refresh_from_db()
        self.assertEqual(self.user1_device.push_token, "user1-token")
        self.assertEqual(self.user1_device.country_code, "US")
        self.assertTrue(self.user1_device.is_revoked)

        user2_row = TrustedDevice.objects.get(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=self.user2,
        )
        self.assertEqual(user2_row.push_token, "user2-token")
        self.assertEqual(user2_row.country_code, "HK")
        self.assertFalse(user2_row.is_revoked)

    def test_unsigned_without_user_id_only_touches_anonymous_row(self):
        self.user2_device = TrustedDevice.objects.create(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=self.user2,
            push_token="user2-token",
            is_revoked=True,
        )
        DeviceService.register_device(
            user=None,
            data={
                "device_id": self.device_id,
                "bundle_id": self.bundle_id,
                "push_token": "anon-only",
            },
            explicit_keys={"device_id", "bundle_id", "push_token"},
            request_id="req-anon-only",
        )
        self.user1_device.refresh_from_db()
        self.user2_device.refresh_from_db()
        self.assertEqual(self.user1_device.push_token, "user1-token")
        self.assertEqual(self.user2_device.push_token, "user2-token")
        anon = TrustedDevice.objects.get(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user__isnull=True,
        )
        self.assertEqual(anon.push_token, "anon-only")

    def test_unsigned_with_user_id_hint_updates_matching_revoked_row(self):
        DeviceService.register_device(
            user=None,
            data={
                "device_id": self.device_id,
                "bundle_id": self.bundle_id,
                "push_token": "unsigned-update",
                "user_id": self.user1.id,
            },
            explicit_keys={
                "device_id",
                "bundle_id",
                "push_token",
                "user_id",
            },
            request_id="req-anon-hint",
        )
        self.user1_device.refresh_from_db()
        self.assertEqual(self.user1_device.push_token, "unsigned-update")
        self.assertFalse(
            TrustedDevice.objects.filter(
                bundle_id=self.bundle_id,
                device_id=self.device_id,
                user__isnull=True,
            ).exists()
        )


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

    def test_login_linking_upgrades_anonymous_row(self):
        from accounts.services.device_linking_service import DeviceLinkingService

        anon_id = self.anon.id
        DeviceLinkingService.ensure_user_device_profile_from_anonymous(
            user=self.user,
            device_id=self.device_id,
            bundle_id=self.bundle_id,
            request_id="req-link",
        )

        self.assertFalse(
            TrustedDevice.objects.filter(
                bundle_id=self.bundle_id,
                device_id=self.device_id,
                user__isnull=True,
            ).exists()
        )
        user_row = TrustedDevice.objects.get(
            bundle_id=self.bundle_id,
            device_id=self.device_id,
            user=self.user,
        )
        self.assertEqual(user_row.id, anon_id)
        self.assertEqual(user_row.country_code, "CN")
        self.assertEqual(user_row.push_token, "anon-token")
        self.assertTrue(user_row.notifications_enabled)
        self.assertFalse(user_row.is_revoked)
