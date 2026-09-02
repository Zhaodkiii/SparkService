"""CHAT-000055：患者端会话能力 + 医院知识 Manifest / 增量 pull 契约测试。"""

from unittest.mock import patch

from django.test import TestCase

from chat_sync.ai_models.knowledge import KnowledgeBase

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import ClinicalAgentKnowledgeBinding, HospitalKnowledgeBaseProfile
from hospital_care.selectors.patient_knowledge import (
    agent_knowledge_manifest,
    conversation_capabilities,
    pull_knowledge_base_delta,
)
from hospital_care.services.conversation_service import create_patient_conversation
from hospital_care.services.hospital_knowledge_service import (
    build_vectors,
    create_document,
    create_knowledge_base,
)
from hospital_care.tests.factories import (
    DummyRequest,
    make_agent,
    make_department,
    make_doctor,
    make_embedding_binding,
    make_hospital,
    make_member,
    make_provider,
    make_user,
)


class PatientKnowledgeContractTests(TestCase):
    def setUp(self):
        self.admin = make_user("kb-admin", is_staff=True, is_superuser=True)
        self.request = DummyRequest(self.admin)
        self.hospital = make_hospital(code="H-SYNC")
        self.department = make_department(self.hospital)
        self.doctor = make_doctor(self.hospital, department=self.department)
        self.agent = make_agent(self.hospital, self.doctor, self.department)
        self.other_agent = make_agent(self.hospital, self.doctor, self.department)
        self.other_agent.name = "另一智能体"
        self.other_agent.save(update_fields=["name"])
        self.patient = make_user("pat-sync")
        self.member = make_member(self.patient)
        make_provider()  # embedding 路由校验要求 company=test 存在可用 provider
        self.profile = create_knowledge_base(
            request=self.request,
            hospital_id=self.hospital.id,
            payload={"name": "就诊须知", "description": "文本库"},
        )

    def _bind(self, agent, profile):
        return ClinicalAgentKnowledgeBinding.objects.create(
            agent=agent,
            knowledge_base_id=profile.knowledge_base_id,
            usage_scope=ClinicalAgentKnowledgeBinding.UsageScope.HOSPITAL,
            status=ClinicalAgentKnowledgeBinding.Status.ACTIVE,
            sort_order=0,
            approved_by=self.admin,
        )

    def test_manifest_only_contains_bound_knowledge_bases(self):
        other_profile = create_knowledge_base(
            request=self.request,
            hospital_id=self.hospital.id,
            payload={"name": "其他库"},
        )
        self._bind(self.agent, self.profile)
        manifest = agent_knowledge_manifest(self.agent)
        ids = [item["knowledge_base_id"] for item in manifest["knowledge_bases"]]
        self.assertIn(str(self.profile.knowledge_base_id), ids)
        self.assertNotIn(str(other_profile.knowledge_base_id), ids)

    def test_unbind_changes_manifest_revision(self):
        binding = self._bind(self.agent, self.profile)
        first = agent_knowledge_manifest(self.agent)
        binding.delete()  # 解绑 = 删除绑定记录（同 _sync_knowledge_bindings 语义）
        second = agent_knowledge_manifest(self.agent)
        self.assertIsNone(second)  # 无生效绑定：Manifest 缺省即全量下线信号
        # 重新绑定后 revision 必须不同
        self._bind(self.agent, self.profile)
        third = agent_knowledge_manifest(self.agent)
        self.assertNotEqual(first["manifest_revision"], third["manifest_revision"])

    def test_pull_returns_content_and_fresh_vectors(self):
        self._bind(self.agent, self.profile)
        create_document(
            request=self.request,
            profile_id=self.profile.id,
            payload={"title": "挂号说明", "content": "请携带身份证", "version": self.profile.version},
        )
        self.profile.refresh_from_db()
        embedding = make_embedding_binding()
        with patch(
            "hospital_care.services.hospital_knowledge_service.EmbeddingGateway.embed",
            return_value=[[0.1, 0.2, 0.3]],
        ):
            build_vectors(
                request=self.request,
                profile_id=self.profile.id,
                embedding_binding_id=embedding.id,
                version=self.profile.version,
            )
        page = pull_knowledge_base_delta(knowledge_base_id=self.profile.knowledge_base_id, cursor=None, limit=100)
        self.assertFalse(page["has_more"])
        self.assertEqual(len(page["documents"]), 1)
        document = page["documents"][0]
        self.assertEqual(document["title"], "挂号说明")
        self.assertEqual(document["content"], "请携带身份证")
        self.assertEqual(len(document["chunks"]), 1)
        chunk = document["chunks"][0]
        self.assertEqual(chunk["document_revision"], document["revision"])
        self.assertEqual(chunk["vector_payload"], [0.1, 0.2, 0.3])
        self.assertEqual(page["vector_status"], HospitalKnowledgeBaseProfile.VectorStatus.CURRENT)

    def test_stale_vectors_not_sent_and_status_not_current(self):
        self._bind(self.agent, self.profile)
        created = create_document(
            request=self.request,
            profile_id=self.profile.id,
            payload={"title": "文本", "content": "内容", "version": self.profile.version},
        )
        self.profile.refresh_from_db()
        embedding = make_embedding_binding()
        with patch(
            "hospital_care.services.hospital_knowledge_service.EmbeddingGateway.embed",
            return_value=[[0.1]],
        ):
            build_vectors(
                request=self.request,
                profile_id=self.profile.id,
                embedding_binding_id=embedding.id,
                version=self.profile.version,
            )
        from hospital_care.services.hospital_knowledge_service import update_document

        update_document(
            request=self.request,
            profile_id=self.profile.id,
            document_id=created.id,
            payload={"title": "文本", "content": "内容-改", "revision": created.revision},
        )
        page = pull_knowledge_base_delta(knowledge_base_id=self.profile.knowledge_base_id, cursor=None, limit=100)
        self.assertEqual(page["vector_status"], HospitalKnowledgeBaseProfile.VectorStatus.STALE)
        self.assertEqual(page["documents"][0]["chunks"], [])

    def test_pull_returns_tombstones_and_invalid_cursor_fails(self):
        self._bind(self.agent, self.profile)
        created = create_document(
            request=self.request,
            profile_id=self.profile.id,
            payload={"title": "将删除", "content": "内容", "version": self.profile.version},
        )
        from chat_sync.ai_models.knowledge import KnowledgeDocument

        KnowledgeDocument.objects.filter(pk=created.id).update(is_deleted=True)
        page = pull_knowledge_base_delta(knowledge_base_id=self.profile.knowledge_base_id, cursor=None, limit=100)
        self.assertEqual(len(page["documents"]), 1)
        self.assertTrue(page["documents"][0]["is_deleted"])
        self.assertEqual(page["documents"][0]["content"], "")
        with self.assertRaises(HospitalCareError) as ctx:
            pull_knowledge_base_delta(
                knowledge_base_id=self.profile.knowledge_base_id,
                cursor="not-a-cursor",
                limit=100,
            )
        self.assertEqual(ctx.exception.error_code, "HOSPITAL_KNOWLEDGE_CURSOR_INVALID")

    def test_pull_incremental_cursor_skips_seen_documents(self):
        self._bind(self.agent, self.profile)
        create_document(
            request=self.request,
            profile_id=self.profile.id,
            payload={"title": "第一篇", "content": "内容一", "version": self.profile.version},
        )
        first_page = pull_knowledge_base_delta(
            knowledge_base_id=self.profile.knowledge_base_id, cursor=None, limit=1
        )
        self.assertEqual(len(first_page["documents"]), 1)
        self.profile.refresh_from_db()
        create_document(
            request=self.request,
            profile_id=self.profile.id,
            payload={"title": "第二篇", "content": "内容二", "version": self.profile.version},
        )
        second_page = pull_knowledge_base_delta(
            knowledge_base_id=self.profile.knowledge_base_id,
            cursor=first_page["cursor"],
            limit=100,
        )
        titles = [item["title"] for item in second_page["documents"]]
        self.assertIn("第二篇", titles)
        self.assertNotIn("第一篇", titles)

    def test_capabilities_for_published_and_unpublished_agent(self):
        self._bind(self.agent, self.profile)
        binding = create_patient_conversation(
            request=DummyRequest(self.patient),
            user=self.patient,
            agent_id=self.agent.id,
            member_id=self.member.id,
        )
        caps = conversation_capabilities(binding)
        self.assertTrue(caps["can_send_message"])
        self.assertTrue(caps["can_sync_knowledge"])
        self.assertIsNone(caps["read_only_reason"])
        self.agent.publication_status = self.agent.PublicationStatus.DISABLED
        self.agent.save(update_fields=["publication_status"])
        binding.refresh_from_db()
        caps = conversation_capabilities(binding)
        self.assertFalse(caps["can_send_message"])
        self.assertFalse(caps["can_pull_remote_messages"])
        self.assertFalse(caps["can_sync_knowledge"])
        self.assertEqual(caps["read_only_reason"], "agent_unpublished")
        # 下架智能体 Manifest 为 None（停止知识同步信号）
        self.assertIsNone(agent_knowledge_manifest(self.agent))

    def test_manifest_revision_matches_kb_revision(self):
        self._bind(self.agent, self.profile)
        manifest = agent_knowledge_manifest(self.agent)
        item = manifest["knowledge_bases"][0]
        kb = KnowledgeBase.objects.get(pk=self.profile.knowledge_base_id)
        self.assertEqual(item["revision"], kb.revision)
        self.assertEqual(item["vector_status"], HospitalKnowledgeBaseProfile.VectorStatus.NOT_BUILT)
        self.assertIsNone(item["indexed_revision"])
