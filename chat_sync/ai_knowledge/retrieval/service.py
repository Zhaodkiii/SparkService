from __future__ import annotations

from chat_sync.ai_knowledge.retrieval.port import KnowledgeRetrievalPort, KnowledgeRetrievalUnavailable, ResolvedKnowledgeChunk


class UnavailableKnowledgeRetrievalService:
    def resolve_chunk(self, *, user, chunk_id: str, revision: int | None = None) -> ResolvedKnowledgeChunk:
        raise KnowledgeRetrievalUnavailable("chat_knowledge_backend_unavailable")

    def search(
        self,
        *,
        user,
        base_ids: list[str],
        query: str,
        top_k: int = 8,
        threshold: float = 0.75,
    ) -> list[ResolvedKnowledgeChunk]:
        return []


class DeepTutorRetrievalAdapter:
    """Optional adapter shape; disabled unless the DeepTutor flag is on."""

    def resolve_chunk(self, *, user, chunk_id: str, revision: int | None = None) -> ResolvedKnowledgeChunk:
        raise KnowledgeRetrievalUnavailable("knowledge_retrieval_unavailable")

    def search(self, *, user, base_ids: list[str], query: str, top_k: int = 8, threshold: float = 0.75) -> list[ResolvedKnowledgeChunk]:
        return []


_unavailable = UnavailableKnowledgeRetrievalService()


def get_retrieval_port() -> KnowledgeRetrievalPort:
    from django.conf import settings

    if getattr(settings, "KNOWLEDGE_DEEPTUTOR_ADAPTER_ENABLED", False):
        return DeepTutorRetrievalAdapter()
    if getattr(settings, "KNOWLEDGE_RAG_TOOL_ENABLED", False):
        from .native import NativeVectorRetrievalService

        return NativeVectorRetrievalService()
    return _unavailable
