from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from accounts.models import AccountDeviceSession, TrustedDevice
from backoffice.models import AdminAuditLog, AdminRole, AdminUserRole
from backoffice.rbac import bootstrap_admin_permissions


User = get_user_model()


class BackofficePermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = User.objects.create_user(
            username="staff_user",
            email="staff@example.com",
            password="pass1234",
            is_staff=True,
        )
        self.normal_user = User.objects.create_user(
            username="normal_user",
            email="normal@example.com",
            password="pass1234",
            is_staff=False,
        )
        self.target_user = User.objects.create_user(
            username="target_user",
            email="target@example.com",
            password="pass1234",
            is_staff=False,
        )

        bootstrap_admin_permissions()
        super_admin = AdminRole.objects.get(code="super_admin")
        AdminUserRole.objects.create(user=self.staff_user, role=super_admin)

    def test_dashboard_allows_staff(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/admin/v1/dashboard/overview/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_blocks_non_staff(self):
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get("/api/admin/v1/dashboard/overview/")
        self.assertEqual(response.status_code, 403)

    def test_admin_login_success(self):
        response = self.client.post(
            "/api/admin/v1/auth/login/",
            {"username": "staff_user", "password": "pass1234"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data["data"])
        access = AccessToken(response.data["data"]["access"])
        refresh = RefreshToken(response.data["data"]["refresh"])
        self.assertEqual(access["exp"] - access["iat"], 24 * 60 * 60)
        self.assertEqual(refresh["exp"] - refresh["iat"], 24 * 60 * 60)

    def test_user_status_update_writes_audit(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(
            f"/api/admin/v1/users/{self.target_user.id}/status/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.target_user.refresh_from_db()
        self.assertFalse(self.target_user.is_active)
        self.assertTrue(AdminAuditLog.objects.filter(action="admin.user.status.update", resource_id=str(self.target_user.id)).exists())

    def test_user_detail_allows_staff(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(f"/api/admin/v1/users/{self.target_user.id}/detail/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["user"]["id"], self.target_user.id)
        self.assertEqual(data["trusted_devices"], [])
        self.assertEqual(data["device_sessions"], [])

    def test_user_detail_blocks_non_staff(self):
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get(f"/api/admin/v1/users/{self.target_user.id}/detail/")
        self.assertEqual(response.status_code, 403)

    def test_user_detail_not_found(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/admin/v1/users/999999/detail/")
        self.assertEqual(response.status_code, 404)

    def test_user_detail_with_devices_and_sessions(self):
        device_old = TrustedDevice.objects.create(
            user=self.target_user,
            bundle_id="cn.Zhaodk.Health",
            device_id="device-old",
            push_token="806a03abcdef1234567890abcdef2386b2",
            platform="iOS",
            system_version="26.2",
            device_model="arm64",
            device_model_name="iPhone",
            device_name="Old iPhone",
            country_code="CN",
            region_code="CN",
            language_code="zh",
            is_simulator=False,
            is_revoked=True,
            request_id="req-old",
        )
        device_new = TrustedDevice.objects.create(
            user=self.target_user,
            bundle_id="cn.Zhaodk.Health",
            device_id="device-new",
            push_token="",
            platform="iOS",
            system_version="26.2",
            device_model="arm64",
            device_model_name="iPhone",
            device_name="New iPhone",
            country_code="CN",
            region_code="CN",
            language_code="zh",
            is_simulator=True,
            is_revoked=False,
            request_id="req-new",
        )
        session_revoked = AccountDeviceSession.objects.create(
            user=self.target_user,
            trusted_device=device_old,
            bundle_id=device_old.bundle_id,
            device_id=device_old.device_id,
            session_version=1,
            status=AccountDeviceSession.Status.REVOKED,
            revoked_reason="replaced_by_new_device",
        )
        session_active = AccountDeviceSession.objects.create(
            user=self.target_user,
            trusted_device=device_new,
            bundle_id=device_new.bundle_id,
            device_id=device_new.device_id,
            session_version=2,
            status=AccountDeviceSession.Status.ACTIVE,
            replaced_by=None,
        )
        session_revoked.replaced_by = session_active
        session_revoked.save(update_fields=["replaced_by"])

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(f"/api/admin/v1/users/{self.target_user.id}/detail/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]

        self.assertEqual(len(data["trusted_devices"]), 2)
        self.assertEqual(data["trusted_devices"][0]["id"], device_new.id)
        self.assertEqual(data["trusted_devices"][1]["id"], device_old.id)
        self.assertEqual(data["trusted_devices"][1]["push_token_masked"], "806a03...2386b2")
        self.assertNotIn("push_token", data["trusted_devices"][1])
        self.assertTrue(data["trusted_devices"][0]["is_simulator"])
        self.assertTrue(data["trusted_devices"][1]["is_revoked"])

        self.assertEqual(len(data["device_sessions"]), 2)
        self.assertEqual(data["device_sessions"][0]["id"], session_active.id)
        self.assertEqual(data["device_sessions"][0]["status"], "active")
        self.assertEqual(data["device_sessions"][1]["id"], session_revoked.id)
        self.assertEqual(data["device_sessions"][1]["status"], "revoked")
        self.assertEqual(data["device_sessions"][1]["replaced_by"], session_active.id)
