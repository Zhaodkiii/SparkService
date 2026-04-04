from django.test import TestCase


class AIBootstrapConfigViewTests(TestCase):
    def test_bootstrap_endpoint_returns_wrapped_payload(self):
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
