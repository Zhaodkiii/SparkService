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
