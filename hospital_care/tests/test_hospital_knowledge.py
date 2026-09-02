from unittest.mock import patch

from django.test import TestCase

from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeDocument
from chat_sync.ai_runtime.providers.exceptions import LLMConfigError

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import HospitalKnowledgeBaseProfile, HospitalKnowledgeChunk
from hospital_care.services.hospital_knowledge_service import (
    build_vectors,
    create_document,
    create_knowledge_base,
    soft_delete_knowledge_base,
    update_document,
)
from hospital_care.tests.factories import (
    DummyRequest,
    make_embedding_binding,
    make_hospital,
    make_provider,
    make_user,
)


class HospitalKnowledgeServiceTests(TestCase):
    def setUp(self):
        self.admin = make_user("kb-admin", is_staff=True, is_superuser=True)
        self.operator = make_user("kb-operator", is_staff=True, is_superuser=True)
        self.request = DummyRequest(self.operator)
        self.hospital = make_hospital(code="KB-H")
        self.provider = make_provider()
        self.embedding = make_embedding_binding()

    def test_create_uses_hospital_service_user(self):
        profile = create_knowledge_base(
            request=self.request,
            hospital_id=self.hospital.id,
            payload={"name": "就诊须知", "description": "文本库"},
        )
        kb = KnowledgeBase.objects.get(pk=profile.knowledge_base_id)
        self.assertNotEqual(kb.user_id, self.operator.id)
        self.assertTrue(kb.user.username.startswith("hospital_kb_svc_"))
        self.assertFalse(kb.user.is_active)
        self.assertEqual(profile.vector_status, HospitalKnowledgeBaseProfile.VectorStatus.NOT_BUILT)
        self.assertEqual(profile.created_by_id, self.operator.id)

    def test_edit_document_marks_vectors_stale(self):
        profile = create_knowledge_base(request=self.request, hospital_id=self.hospital.id, payload={"name": "须知"})
        created = create_document(
            request=self.request,
            profile_id=profile.id,
            payload={"title": "挂号说明", "content": "请携带身份证", "version": profile.version},
        )
        profile.refresh_from_db()
        with patch(
            "hospital_care.services.hospital_knowledge_service.EmbeddingGateway.embed",
            return_value=[[0.1, 0.2, 0.3]],
        ):
            built = build_vectors(
                request=self.request,
                profile_id=profile.id,
                embedding_binding_id=self.embedding.id,
                version=profile.version,
            )
        self.assertEqual(built.vector_status, HospitalKnowledgeBaseProfile.VectorStatus.CURRENT)
        self.assertEqual(HospitalKnowledgeChunk.objects.filter(profile=built).count(), 1)
        update_document(
            request=self.request,
            profile_id=profile.id,
            document_id=created.id,
            payload={"title": "挂号说明", "content": "请携带身份证和医保卡", "revision": created.revision},
        )
        profile.refresh_from_db()
        kb = KnowledgeBase.objects.get(pk=profile.knowledge_base_id)
        self.assertEqual(profile.vector_status, HospitalKnowledgeBaseProfile.VectorStatus.STALE)
        self.assertGreater(kb.revision, built.indexed_revision)

    def test_embedding_unavailable_leaves_no_chunks(self):
        profile = create_knowledge_base(request=self.request, hospital_id=self.hospital.id, payload={"name": "须知"})
        create_document(
            request=self.request,
            profile_id=profile.id,
            payload={"title": "文本", "content": "内容", "version": profile.version},
        )
        profile.refresh_from_db()
        with patch(
            "hospital_care.services.hospital_knowledge_service.EmbeddingGateway.embed",
            side_effect=LLMConfigError("no provider"),
        ):
            with self.assertRaises(HospitalCareError) as ctx:
                build_vectors(
                    request=self.request,
                    profile_id=profile.id,
                    embedding_binding_id=self.embedding.id,
                    version=profile.version,
                )
        self.assertEqual(ctx.exception.error_code, "HOSPITAL_KNOWLEDGE_EMBEDDING_UNAVAILABLE")
        self.assertEqual(HospitalKnowledgeChunk.objects.filter(profile=profile).count(), 0)
        profile.refresh_from_db()
        self.assertEqual(profile.vector_status, HospitalKnowledgeBaseProfile.VectorStatus.NOT_BUILT)

    def test_soft_deleted_cannot_be_bound(self):
        from hospital_care.services.agent_provisioning_service import create_clinical_agent
        from hospital_care.tests.factories import make_department, make_doctor
        from ai_config.models import AIModelCatalog

        AIModelCatalog.objects.get_or_create(
            name="hospital-care-test-model",
            defaults={"display_name": "Test Model", "company": "test", "is_active": True},
        )
        profile = create_knowledge_base(request=self.request, hospital_id=self.hospital.id, payload={"name": "须知"})
        soft_delete_knowledge_base(request=self.request, profile_id=profile.id, version=profile.version)
        department = make_department(self.hospital)
        doctor = make_doctor(self.hospital, department=department)
        with self.assertRaises(HospitalCareError) as ctx:
            create_clinical_agent(
                request=self.request,
                hospital_id=self.hospital.id,
                payload={
                    "doctor_id": doctor.id,
                    "department_id": department.id,
                    "name": "助手",
                    "binding": {"model": "hospital-care-test-model", "temperature": 0.2, "max_tokens": 128},
                    "knowledge_bases": [{"profile_id": profile.id}],
                },
            )
        self.assertEqual(ctx.exception.error_code, "HOSPITAL_KNOWLEDGE_NOT_FOUND")
