from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from chat_sync.ai_knowledge.retrieval.native import NativeVectorRetrievalService
from chat_sync.ai_knowledge.retrieval.service import get_retrieval_port
from chat_sync.ai_knowledge.services.chunker import chunk_text
from chat_sync.ai_knowledge.services.index_pipeline import index_document
from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeDocument, KnowledgeIndexStatus


class KnowledgeChunkerTests(TestCase):
    def test_chunks_long_text(self):
        text = "血糖 " * 400
        chunks = chunk_text(text, size=80, overlap=10)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0]["sequence"], 0)


class NativeRetrievalTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="kb-retr-user")
        self.base = KnowledgeBase.objects.create(user=self.user, name="随访")
        self.document = KnowledgeDocument.objects.create(
            id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            user=self.user,
            knowledge_base=self.base,
            title="空腹血糖",
            content="空腹血糖随访应关注夜间低血糖风险。",
        )

    @override_settings(KNOWLEDGE_RAG_TOOL_ENABLED=True)
    def test_lexical_search_after_index_without_embedding_provider(self):
        index_document(str(self.document.id), self.document.revision)
        self.document.refresh_from_db()
        self.assertTrue(KnowledgeChunk.objects.filter(document=self.document).exists())
        hits = NativeVectorRetrievalService().search(
            user=self.user,
            base_ids=[str(self.base.id)],
            query="低血糖",
            top_k=5,
            threshold=0.1,
        )
        self.assertTrue(hits)
        self.assertEqual(hits[0].document_id, str(self.document.id))

    def test_default_port_still_unavailable_when_flag_off(self):
        from chat_sync.ai_knowledge.retrieval.port import KnowledgeRetrievalUnavailable

        with self.assertRaises(KnowledgeRetrievalUnavailable):
            get_retrieval_port().resolve_chunk(user=self.user, chunk_id="missing")
