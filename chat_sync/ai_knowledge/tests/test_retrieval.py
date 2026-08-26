from django.contrib.auth import get_user_model
from django.test import TestCase

from chat_sync.ai_knowledge.retrieval.port import KnowledgeRetrievalUnavailable
from chat_sync.ai_knowledge.retrieval.service import get_retrieval_port
from chat_sync.ai_services.context.reference_resolver import ReferenceResolutionError, resolve_references
from chat_sync.models import ChatThread


class KnowledgeRetrievalPortStubTests(TestCase):
    """P2 检索端口本轮只冻结接口：默认实现始终不可用，但调用点已经解耦。"""

    def test_default_port_raises_unavailable_for_resolve_chunk(self):
        user = get_user_model().objects.create_user(username="retrieval-user")
        with self.assertRaises(KnowledgeRetrievalUnavailable):
            get_retrieval_port().resolve_chunk(user=user, chunk_id="chunk-1")

    def test_default_port_search_returns_empty_list(self):
        user = get_user_model().objects.create_user(username="retrieval-search-user")
        results = get_retrieval_port().search(user=user, base_ids=["base-1"], query="q")
        self.assertEqual(results, [])

    def test_reference_resolver_routes_through_port_and_preserves_error_code(self):
        user = get_user_model().objects.create_user(username="retrieval-resolver-user")
        thread = ChatThread.objects.create(user=user, title="knowledge-ref")

        with self.assertRaises(ReferenceResolutionError) as ctx:
            resolve_references(
                user=user,
                thread=thread,
                references=[{"type": "knowledge_chunk", "chunk_id": "chunk-1"}],
                attachments=[],
            )
        self.assertEqual(ctx.exception.code, "chat_knowledge_backend_unavailable")
