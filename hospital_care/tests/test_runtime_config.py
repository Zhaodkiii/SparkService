import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from hospital_care.models import ClinicalAgentProfile, ClinicalConversationBinding
from hospital_care.tests.factories import (
    make_agent,
    make_department,
    make_doctor,
    make_hospital,
    make_member,
    make_provider,
    make_scenario_binding,
    make_user,
)


class AgentRuntimeConfigApiTests(TestCase):
    """CHAT-000058：GET /api/v1/hospital-care/agents/{agent_id}/runtime-config/ 契约测试。"""

    def setUp(self):
        self.client = APIClient()
        self.patient = make_user("rc-patient")
        self.member = make_member(self.patient)
        self.hospital = make_hospital(code="RC-H")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department)
        make_provider()
        self.binding = make_scenario_binding()
        self.agent = make_agent(self.hospital, self.doctor, self.department, scenario=self.binding)
        self.client.force_authenticate(self.patient)

    def _url(self, agent_id=None):
        return f"/api/v1/hospital-care/agents/{agent_id or self.agent.id}/runtime-config/"

    def test_runtime_config_success(self):
        response = self.client.get(self._url(), {"member_id": self.member.id})
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]

        self.assertEqual(data["agent_id"], str(self.agent.id))
        self.assertEqual(data["hospital_id"], str(self.hospital.id))
        self.assertEqual(data["member_id"], self.member.id)
        self.assertEqual(data["doctor"]["name"], self.doctor.display_name)
        self.assertEqual(data["doctor"]["department_name"], self.department.name)
        self.assertEqual(data["profile"]["name"], self.agent.name)
        self.assertEqual(data["profile"]["status"], ClinicalAgentProfile.PublicationStatus.PUBLISHED)

        runtime = data["runtime"]
        self.assertEqual(runtime["binding_id"], self.binding.id)
        self.assertTrue(runtime["config_version"].startswith(f"{self.binding.id}:"))

        model = runtime["model"]
        self.assertEqual(model["name"], self.binding.bootstrap_name())
        self.assertEqual(model["identity"], "agent")
        self.assertEqual(model["baseModelName"], self.binding.model.name)
        self.assertEqual(model["endpoint"], "https://example.test/v1/chat/completions")
        self.assertEqual(model["api_key"], "sk-test")
        self.assertEqual(model["source"], "hospital")
        self.assertEqual(model["aiScenarios"], ["chat"])
        self.assertFalse(model["is_default"])

    def test_missing_member_id_rejected(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["msg"], "PAYLOAD_INVALID")

    def test_stranger_member_denied(self):
        stranger = make_user("rc-stranger")
        stranger_member = make_member(stranger)
        response = self.client.get(self._url(), {"member_id": stranger_member.id})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["msg"], "MEMBER_ACCESS_DENIED")

    def test_unknown_agent(self):
        response = self.client.get(self._url(uuid.uuid4()), {"member_id": self.member.id})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["msg"], "AGENT_NOT_FOUND")

    def test_unpublished_agent_unavailable(self):
        self.agent.publication_status = ClinicalAgentProfile.PublicationStatus.DISABLED
        self.agent.save(update_fields=["publication_status"])
        response = self.client.get(self._url(), {"member_id": self.member.id})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["msg"], "AGENT_UNAVAILABLE")

    def test_inactive_binding_invalid(self):
        self.binding.is_active = False
        self.binding.save(update_fields=["is_active"])
        response = self.client.get(self._url(), {"member_id": self.member.id})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["msg"], "AGENT_BINDING_INVALID")

    def test_missing_provider_config_invalid(self):
        from ai_config.models import AIProviderKeyConfig

        AIProviderKeyConfig.objects.all().delete()
        response = self.client.get(self._url(), {"member_id": self.member.id})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["msg"], "RUNTIME_CONFIG_INVALID")

    def test_error_response_never_carries_model_candidates(self):
        self.agent.publication_status = ClinicalAgentProfile.PublicationStatus.DISABLED
        self.agent.save(update_fields=["publication_status"])
        response = self.client.get(self._url(), {"member_id": self.member.id})
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("endpoint", str(response.data.get("data")))
        self.assertNotIn("api_key", str(response.data.get("data")))


class ConversationBindingFixTests(TestCase):
    """CHAT-000058：创建医院 Thread 时服务端重解析并固定 AIScenarioModelBinding。"""

    def setUp(self):
        self.client = APIClient()
        self.patient = make_user("bf-patient")
        self.member = make_member(self.patient)
        self.hospital = make_hospital(code="BF-H")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department)
        make_provider()
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.client.force_authenticate(self.patient)

    def test_create_conversation_fixes_scenario_binding(self):
        response = self.client.post(
            "/api/v1/hospital-care/conversations/",
            {"agent_id": str(self.agent.id), "member_id": self.member.id},
            format="json",
            HTTP_IDEMPOTENCY_KEY="bf-create-1",
        )
        self.assertEqual(response.status_code, 200, response.data)
        conversation = response.data["data"]["conversation"]
        self.assertEqual(conversation["binding_id"], self.agent.scenario_binding_id)
        self.assertIsNotNone(conversation["binding_version"])

        binding = ClinicalConversationBinding.objects.get(thread_id=response.data["data"]["thread_id"])
        self.assertEqual(binding.scenario_binding_id, self.agent.scenario_binding_id)

    def test_create_conversation_rejected_when_binding_inactive(self):
        scenario_binding = self.agent.scenario_binding
        scenario_binding.is_active = False
        scenario_binding.save(update_fields=["is_active"])

        response = self.client.post(
            "/api/v1/hospital-care/conversations/",
            {"agent_id": str(self.agent.id), "member_id": self.member.id},
            format="json",
            HTTP_IDEMPOTENCY_KEY="bf-create-2",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["msg"], "AGENT_BINDING_INVALID")
        self.assertEqual(ClinicalConversationBinding.objects.count(), 0)
