from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from ai_config.models import (
    AIModelCatalog,
    AIProviderKeyConfig,
    AIScenarioModelBinding,
    IdentityKind,
    ScenarioKey,
    TrialApplication,
)


class AIBootstrapConfigViewTests(APITestCase):
    EXPECTED_SCENARIOS = set(ScenarioKey.values)

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
        self.assertEqual(payload["data"]["scenarios"], {})
        self.assertEqual(payload["data"]["smallTasks"], [])
        self.assertEqual(payload["data"]["trial_status"], "none")

    def test_bootstrap_scenarios_multi_model_shape(self):
        """An active trial receives only retained client model scenarios."""
        now = timezone.now()
        TrialApplication.objects.create(user=self.user, status=TrialApplication.Status.ACTIVE,
            started_at=now, expires_at=now + timedelta(days=1))
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/v1/ai/config/bootstrap/")
        self.assertEqual(response.status_code, 200)
        scenarios = response.json()["data"]["scenarios"]
        self.assertIsInstance(scenarios, dict)
        self.assertEqual(set(scenarios.keys()), self.EXPECTED_SCENARIOS)
        for _key, block in scenarios.items():
            self.assertIn("default_model", block)
            self.assertIn("models", block)
            self.assertIsInstance(block["models"], list)
            for row in block["models"]:
                self.assertIn("name", row)
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
        self.assertTrue(apply_payload["submitted"])
        self.assertEqual(apply_payload["status"], "pending")

        status_resp = self.client.get("/api/v1/ai/trial/status/")
        self.assertEqual(status_resp.status_code, 200)
        status_payload = status_resp.json()["data"]
        self.assertFalse(status_payload["is_active"])

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


class AIBootstrapMultiAgentTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="pro-user", email="pro@example.com", password="secret123")
        now = timezone.now()
        TrialApplication.objects.create(
            user=self.user,
            status=TrialApplication.Status.ACTIVE,
            started_at=now,
            expires_at=now + timedelta(days=7),
        )
        AIProviderKeyConfig.objects.create(
            kind=AIProviderKeyConfig.Kind.API,
            name="Test Provider",
            company="TESTCO",
            key="test-key",
            request_url="https://api.example.com/v1",
            is_using=True,
        )
        self.catalog_model = AIModelCatalog.objects.create(
            name="deepseek-v4-pro",
            display_name="DeepSeek V4 Pro",
            company="TESTCO",
        )
        self.agent_one = AIScenarioModelBinding.objects.create(
            scenario=ScenarioKey.CHAT,
            model=self.catalog_model,
            display_name="报告解读助手",
            identity=IdentityKind.AGENT,
            brief_description="报告解读智能体",
            position=1,
        )
        self.agent_two = AIScenarioModelBinding.objects.create(
            scenario=ScenarioKey.CHAT,
            model=self.catalog_model,
            display_name="用药建议助手",
            identity=IdentityKind.AGENT,
            brief_description="用药顾问",
            position=2,
            is_default=True,
        )

    def test_bootstrap_returns_distinct_agent_names_and_base_model_name(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/v1/ai/config/bootstrap/")
        self.assertEqual(response.status_code, 200)

        chat = response.json()["data"]["scenarios"]["chat"]
        names = [row["name"] for row in chat["models"]]
        self.assertEqual(len(names), 2)
        self.assertEqual(len(set(names)), 2)
        self.assertEqual(
            names,
            [
                self.agent_one.bootstrap_name(),
                self.agent_two.bootstrap_name(),
            ],
        )

        for row in chat["models"]:
            self.assertEqual(row["identity"], IdentityKind.AGENT)
            self.assertEqual(row["baseModelName"], self.catalog_model.name)

        self.assertEqual(chat["default_model"], self.agent_two.bootstrap_name())

    def test_bootstrap_agent_rows_keep_separate_prompt_fields(self):
        self.agent_one.system_provision = "agent-one-system"
        self.agent_one.save(update_fields=["system_provision"])
        self.agent_two.system_provision = "agent-two-system"
        self.agent_two.save(update_fields=["system_provision"])

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/v1/ai/config/bootstrap/")
        self.assertEqual(response.status_code, 200)

        by_name = {row["name"]: row for row in response.json()["data"]["scenarios"]["chat"]["models"]}
        self.assertEqual(by_name[self.agent_one.bootstrap_name()]["systemProvision"], "agent-one-system")
        self.assertEqual(by_name[self.agent_two.bootstrap_name()]["systemProvision"], "agent-two-system")

    def test_bootstrap_uses_binding_display_name_not_catalog(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/v1/ai/config/bootstrap/")
        self.assertEqual(response.status_code, 200)

        by_name = {row["name"]: row for row in response.json()["data"]["scenarios"]["chat"]["models"]}
        self.assertEqual(by_name[self.agent_one.bootstrap_name()]["display_name"], "报告解读助手")
        self.assertEqual(by_name[self.agent_two.bootstrap_name()]["display_name"], "用药建议助手")
        self.assertNotEqual(by_name[self.agent_one.bootstrap_name()]["display_name"], self.catalog_model.display_name)

    def test_bootstrap_falls_back_to_catalog_display_name_when_binding_display_name_empty(self):
        self.agent_one.display_name = ""
        self.agent_one.save(update_fields=["display_name"])

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/v1/ai/config/bootstrap/")
        self.assertEqual(response.status_code, 200)

        by_name = {row["name"]: row for row in response.json()["data"]["scenarios"]["chat"]["models"]}
        self.assertEqual(by_name[self.agent_one.bootstrap_name()]["display_name"], self.catalog_model.display_name)
