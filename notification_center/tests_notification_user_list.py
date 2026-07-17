from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from backoffice.models import AdminRole, AdminUserRole
from backoffice.rbac import bootstrap_admin_permissions
from notification_center.services import NotificationCenterService

User = get_user_model()

LIST_URL = "/api/admin/v1/notification-center/notifications/users/"


class NotificationUserListApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = User.objects.create_user(
            username="staff_user",
            email="staff@example.com",
            password="pass1234",
            is_staff=True,
        )
        User.objects.create_user(
            username="notify_target",
            email="target@example.com",
            password="pass1234",
            is_staff=False,
        )
        bootstrap_admin_permissions()
        super_admin = AdminRole.objects.get(code="super_admin")
        AdminUserRole.objects.create(user=self.staff_user, role=super_admin)
        self.client.force_authenticate(user=self.staff_user)

    def test_list_users_with_string_query_params_returns_200(self):
        response = self.client.get(
            LIST_URL,
            {
                "page": "1",
                "page_size": "20",
                "q": "",
                "only_enabled": "true",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["code"], 0)
        self.assertIn("items", response.data["data"])
        pagination = response.data["data"]["pagination"]
        self.assertIsInstance(pagination["page"], int)
        self.assertIsInstance(pagination["page_size"], int)
        self.assertEqual(pagination["page"], 1)
        self.assertEqual(pagination["page_size"], 20)

    def test_only_enabled_false_is_parsed_as_boolean(self):
        response = self.client.get(LIST_URL, {"only_enabled": "false", "page": "1", "page_size": "20"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["code"], 0)

    def test_invalid_page_returns_400(self):
        response = self.client.get(LIST_URL, {"page": "abc", "page_size": "20"})

        self.assertEqual(response.status_code, 400)

    def test_page_size_above_max_returns_400(self):
        response = self.client.get(LIST_URL, {"page": "1", "page_size": "10000"})

        self.assertEqual(response.status_code, 400)


class NotificationUserListServiceTests(TestCase):
    def setUp(self):
        User.objects.create_user(
            username="service_target",
            email="service@example.com",
            password="pass1234",
            is_staff=False,
        )

    def test_list_notification_users_coerces_string_pagination(self):
        result = NotificationCenterService.list_notification_users(page="2", page_size="10")

        self.assertEqual(result["pagination"]["page"], 2)
        self.assertEqual(result["pagination"]["page_size"], 10)
        self.assertIsInstance(result["pagination"]["page"], int)
        self.assertIsInstance(result["pagination"]["page_size"], int)

    def test_list_notification_users_coerces_string_only_enabled_false(self):
        with_only_enabled = NotificationCenterService.list_notification_users(only_enabled="true")
        without_only_enabled = NotificationCenterService.list_notification_users(only_enabled="false")

        self.assertGreaterEqual(without_only_enabled["pagination"]["total"], with_only_enabled["pagination"]["total"])

    def test_list_notification_users_clamps_oversized_page_size(self):
        result = NotificationCenterService.list_notification_users(page_size="10000")

        self.assertEqual(result["pagination"]["page_size"], 100)
