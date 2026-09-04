from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from ai_config.models import AIModelCatalog

from hospital_care.models import (
    ClinicalAgentProfile,
    DoctorProfile,
    Hospital,
    HospitalKnowledgeBaseProfile,
    HospitalKnowledgeChunk,
    HospitalStaffMembership,
)
from hospital_care.tests.factories import make_embedding_binding, make_provider, make_scenario_binding, make_user


class TianchangAgentKnowledgeE2ETests(TestCase):
    def setUp(self):
        make_scenario_binding(model_name="tianchang-e2e-chat-model")
        call_command("seed_tianchang_hospital", code="000001", activate=True)
        self.hospital = Hospital.objects.get(code="000001")
        self.admin = make_user("tianchang-bo", is_staff=True, is_superuser=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        make_provider()
        AIModelCatalog.objects.get_or_create(
            name="hospital-care-test-model",
            defaults={"display_name": "Test Model", "company": "test", "is_active": True},
        )
        self.embedding = make_embedding_binding()

    def test_create_agent_bind_knowledge_and_build_vectors(self):
        doctor = DoctorProfile.objects.select_related("staff_membership").filter(
            staff_membership__hospital=self.hospital,
            staff_membership__role=HospitalStaffMembership.Role.DOCTOR,
            profile_status=DoctorProfile.ProfileStatus.ACTIVE,
        ).first()
        membership = doctor.department_memberships.select_related("department").first()
        self.assertIsNotNone(membership)
        department = membership.department
        kb = self.client.post(
            f"/api/admin/v1/hospital-care/hospitals/{self.hospital.id}/knowledge-bases/",
            {
                "name": "天长中医院就诊须知",
                "description": "演示知识库",
                "department_ids": [str(department.id)],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="tc-kb",
        )
        self.assertEqual(kb.status_code, 201, kb.data)
        profile_id = kb.data["data"]["id"]
        doc = self.client.post(
            f"/api/admin/v1/hospital-care/knowledge-bases/{profile_id}/documents/",
            {
                "title": "门诊挂号说明",
                "content": "患者请携带身份证和医保卡，先到窗口或自助机挂号后再候诊。",
                "version": kb.data["data"]["version"],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="tc-doc",
        )
        self.assertEqual(doc.status_code, 201, doc.data)
        created = self.client.post(
            f"/api/admin/v1/hospital-care/hospitals/{self.hospital.id}/agents/",
            {
                "doctor_id": str(doctor.id),
                "department_id": str(department.id),
                "name": f"{doctor.display_name} 智能助手",
                "public_summary": "提供就诊须知与科室咨询",
                "greeting": "您好，我是天长市中医院智能助手。",
                "service_boundary": "健康信息与就医指导，不提供确诊。",
                "binding": {"model": "hospital-care-test-model", "temperature": 0.2, "max_tokens": 2048},
                "knowledge_bases": [{"profile_id": profile_id}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="tc-agent",
        )
        self.assertEqual(created.status_code, 201, created.data)
        agent = ClinicalAgentProfile.objects.get(pk=created.data["data"]["id"])
        self.assertEqual(agent.hospital_id, self.hospital.id)
        self.assertEqual(agent.knowledge_bindings.count(), 1)
        profile = HospitalKnowledgeBaseProfile.objects.get(pk=profile_id)
        with patch(
            "hospital_care.services.hospital_knowledge_service.EmbeddingGateway.embed",
            return_value=[[0.11, 0.22, 0.33]],
        ):
            built = self.client.post(
                f"/api/admin/v1/hospital-care/knowledge-bases/{profile_id}/vector-build/",
                {"version": profile.version, "embedding_binding_id": self.embedding.id},
                format="json",
                HTTP_IDEMPOTENCY_KEY="tc-vec",
            )
        self.assertEqual(built.status_code, 200, built.data)
        self.assertEqual(built.data["data"]["vector_status"], HospitalKnowledgeBaseProfile.VectorStatus.CURRENT)
        self.assertEqual(HospitalKnowledgeChunk.objects.filter(profile_id=profile_id).count(), 1)
