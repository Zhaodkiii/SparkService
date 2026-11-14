from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import resolve, Resolver404
from django.apps import apps
from rest_framework.test import APIClient
from ai_production.models import ProductionPolicy


class RetiredAIConfigurationTests(TestCase):
    def test_old_routes_are_removed(self):
        for path in (
            "/api/v1/ai/config/bootstrap/", "/api/v1/ai/trial/status/",
            "/api/v1/ai/trial/apply/", "/api/v1/ai/providers/test-connection/",
            "/api/admin/v1/ai/scenarios/", "/api/admin/v1/ai/models/",
            "/api/admin/v1/ai/providers/", "/api/admin/v1/ai/small-tasks/",
            "/api/admin/v1/ai/trials/", "/api/admin/v1/users/1/pro/grant/",
            "/api/admin/v1/users/1/pro/recycle/",
        ):
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(path)

    def test_retired_models_absent_production_retained(self):
        self.assertFalse(apps.is_installed("ai_config"))
        self.assertIsNotNone(apps.get_model("ai_production", "ProductionTask"))

    def test_account_can_use_production_without_trial(self):
        user = get_user_model().objects.create_user(username="developer")
        ProductionPolicy.objects.create(name="development", short_limit_points=3, weekly_limit_points=10, reason="test")
        client = APIClient()
        client.force_authenticate(user)
        response = client.get("/api/v1/ai-production/quota/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["entitled"])
        self.assertEqual(response.data["data"]["service_status"], "available")


    def test_user_quota_lookup_does_not_start_windows(self):
        from ai_production.models import ProductionWindow

        admin = get_user_model().objects.create_superuser(username="quota-list-admin", password="test")
        get_user_model().objects.create_user(username="quota-reader")
        ProductionPolicy.objects.create(name="list", short_limit_points=3, weekly_limit_points=10)
        client = APIClient()
        client.force_authenticate(admin)
        url = "/api/admin/v1/ai-production/users/"
        items = client.get(url, {"q": "quota-reader"}).data["data"]["items"]
        self.assertEqual(items, [])
        self.assertEqual(ProductionWindow.objects.count(), 0)
        self.assertEqual(client.get(url, {"q": "nonexistent"}).data["data"]["items"], [])

    def test_user_quota_list_pagination_and_access(self):
        admin = get_user_model().objects.create_superuser(username="quota-page-admin", password="test")
        customer = get_user_model().objects.create_user(username="quota-customer")
        ProductionPolicy.objects.create(name="list", short_limit_points=3, weekly_limit_points=10, reason="test")
        client = APIClient()
        client.force_authenticate(customer)
        self.assertEqual(client.get("/api/admin/v1/ai-production/users/").status_code, 403)
        client.force_authenticate(admin)
        response = client.get("/api/admin/v1/ai-production/users/", {"page_size":1})
        self.assertEqual(response.data["data"]["pagination"]["total"], 0)
        self.assertEqual(response.data["data"]["items"], [])
