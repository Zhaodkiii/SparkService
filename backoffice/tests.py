from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

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
