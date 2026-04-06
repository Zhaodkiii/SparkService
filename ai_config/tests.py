from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from ai_config.models import TrialApplication


class AIBootstrapConfigViewTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="trial-user", email="trial@example.com", password="secret123")

    def test_bootstrap_endpoint_returns_wrapped_payload(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/v1/ai/config/bootstrap/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["code"], 0)
        self.assertIn("revision", payload["data"])
        self.assertIn("scenarios", payload["data"])
        self.assertIn("api_keys", payload["data"])
        self.assertIn("search_keys", payload["data"])
        self.assertIn("tool_keys", payload["data"])
        self.assertIn("all_models", payload["data"])
        self.assertIn("user_info", payload["data"])
        self.assertIn("trial", payload["data"])
        self.assertIn("trial_model_policy", payload["data"])

    def test_bootstrap_scenarios_multi_model_shape(self):
        """Each scenario key must expose default_model + models[] (client multi-model contract)."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/v1/ai/config/bootstrap/")
        self.assertEqual(response.status_code, 200)
        scenarios = response.json()["data"]["scenarios"]
        self.assertIsInstance(scenarios, dict)
        for _key, block in scenarios.items():
            self.assertIn("default_model", block)
            self.assertIn("models", block)
            self.assertIsInstance(block["models"], list)
            for row in block["models"]:
                self.assertIn("model", row)
                self.assertIn("is_default", row)

    def test_bootstrap_requires_authenticated_user(self):
        response = self.client.get("/api/v1/ai/config/bootstrap/")
        self.assertEqual(response.status_code, 401)

    def test_apply_trial_then_get_status(self):
        self.client.force_authenticate(user=self.user)

        apply_resp = self.client.post(
            "/api/v1/ai/trial/apply/",
            {"note": "need trial for evaluation"},
            content_type="application/json",
        )
        self.assertEqual(apply_resp.status_code, 200)
        apply_payload = apply_resp.json()["data"]
        self.assertEqual(apply_payload["status"], TrialApplication.Status.ACTIVE)
        self.assertEqual(apply_payload["is_active"], True)

        status_resp = self.client.get("/api/v1/ai/trial/status/")
        self.assertEqual(status_resp.status_code, 200)
        status_payload = status_resp.json()["data"]
        self.assertEqual(status_payload["status"], TrialApplication.Status.ACTIVE)
        self.assertEqual(status_payload["is_active"], True)

    def test_provider_connection_test_validates_input(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(
            "/api/v1/ai/providers/test-connection/",
            {"request_url": "", "api_key": ""},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()["data"]
        self.assertEqual(payload["reachable"], False)
