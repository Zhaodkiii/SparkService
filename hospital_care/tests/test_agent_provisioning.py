from django.test import TestCase

from ai_config.models import AIModelCatalog, AIScenarioModelBinding, IdentityKind, ScenarioKey

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import ClinicalAgentKnowledgeBinding, ClinicalAgentProfile
from hospital_care.services.agent_provisioning_service import create_clinical_agent, update_clinical_agent
from hospital_care.services.hospital_knowledge_service import create_knowledge_base
from hospital_care.tests.factories import (
    DummyRequest,
    make_department,
    make_doctor,
    make_hospital,
    make_provider,
    make_user,
)


class AgentProvisioningTests(TestCase):
    def setUp(self):
        self.admin = make_user("agent-admin", is_staff=True, is_superuser=True)
        self.request = DummyRequest(self.admin)
        self.hospital = make_hospital(code="AG-H")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department, display_name="王医生")
        self.provider = make_provider()
        AIModelCatalog.objects.get_or_create(
            name="hospital-care-test-model",
            defaults={"display_name": "Test Model", "company": "test", "is_active": True},
        )
        self.kb = create_knowledge_base(
            request=self.request,
            hospital_id=self.hospital.id,
            payload={"name": "院内须知", "description": "测试库"},
        )

    def _payload(self, **overrides):
        data = {
            "doctor_id": self.doctor.id,
            "department_id": self.department.id,
            "name": "王医生 AI 助手",
            "public_summary": "院内咨询",
            "greeting": "您好",
            "service_boundary": "健康信息与就医指导，不提供确诊。",
            "binding": {
                "model": "hospital-care-test-model",
                "temperature": 0.2,
                "max_tokens": 2048,
                "system_provision": "你是医院助手",
                "brief_description": "内部简介",
                "ai_tool_scenarios": [],
                "server_tool_scenarios": [],
            },
            "knowledge_bases": [{"profile_id": self.kb.id}],
        }
        data.update(overrides)
        return data

    def test_create_writes_binding_profile_and_knowledge(self):
        from ai_config.models import AIModelCatalog

        AIModelCatalog.objects.get_or_create(
            name="hospital-care-test-model",
            defaults={"display_name": "Test Model", "company": "test", "is_active": True},
        )
        default_binding = AIScenarioModelBinding.objects.create(
            scenario=ScenarioKey.CHAT,
            identity=IdentityKind.MODEL,
            model=AIModelCatalog.objects.get(name="hospital-care-test-model"),
            is_default=True,
            is_active=True,
        )
        agent = create_clinical_agent(request=self.request, hospital_id=self.hospital.id, payload=self._payload())
        self.assertEqual(agent.publication_status, ClinicalAgentProfile.PublicationStatus.DRAFT)
        self.assertEqual(agent.scenario_binding.identity, IdentityKind.AGENT)
        self.assertFalse(agent.scenario_binding.is_default)
        self.assertEqual(agent.scenario_binding.scenario, ScenarioKey.CHAT)
        self.assertEqual(agent.knowledge_bindings.count(), 1)
        self.assertEqual(agent.knowledge_bindings.first().usage_scope, ClinicalAgentKnowledgeBinding.UsageScope.HOSPITAL)
        default_binding.refresh_from_db()
        self.assertTrue(default_binding.is_default)

    def test_two_agents_for_same_doctor(self):
        from ai_config.models import AIModelCatalog

        AIModelCatalog.objects.get_or_create(
            name="hospital-care-test-model",
            defaults={"display_name": "Test Model", "company": "test", "is_active": True},
        )
        first = create_clinical_agent(request=self.request, hospital_id=self.hospital.id, payload=self._payload(name="助手A"))
        second = create_clinical_agent(request=self.request, hospital_id=self.hospital.id, payload=self._payload(name="助手B"))
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(ClinicalAgentProfile.objects.filter(doctor=self.doctor).count(), 2)

    def test_invalid_model_rolls_back(self):
        with self.assertRaises(HospitalCareError) as ctx:
            create_clinical_agent(
                request=self.request,
                hospital_id=self.hospital.id,
                payload=self._payload(binding={"model": "missing-model", "temperature": 0.1, "max_tokens": 128}),
            )
        self.assertEqual(ctx.exception.error_code, "AGENT_BASE_MODEL_UNAVAILABLE")
        self.assertEqual(ClinicalAgentProfile.objects.count(), 0)
        self.assertEqual(AIScenarioModelBinding.objects.filter(identity=IdentityKind.AGENT).count(), 0)

    def test_update_published_moves_to_review(self):
        from ai_config.models import AIModelCatalog

        AIModelCatalog.objects.get_or_create(
            name="hospital-care-test-model",
            defaults={"display_name": "Test Model", "company": "test", "is_active": True},
        )
        agent = create_clinical_agent(request=self.request, hospital_id=self.hospital.id, payload=self._payload())
        agent.publication_status = ClinicalAgentProfile.PublicationStatus.PUBLISHED
        agent.save(update_fields=["publication_status"])
        updated = update_clinical_agent(
            request=self.request,
            agent_id=agent.id,
            payload={"version": agent.version, "name": "更新后的助手", "knowledge_bases": []},
        )
        self.assertEqual(updated.publication_status, ClinicalAgentProfile.PublicationStatus.REVIEW)
        self.assertEqual(updated.knowledge_bindings.count(), 0)
        self.assertEqual(updated.name, "更新后的助手")
