from __future__ import annotations

from .port import KnowledgeRetrievalPort, KnowledgeRetrievalUnavailable, ResolvedKnowledgeChunk


class UnavailableKnowledgeRetrievalService:
    """`KnowledgeRetrievalPort` 的 P2 占位实现。

    本轮（P0/P1/P1.5）不接入分块/Embedding/向量库，检索端口只是被冻结下来，
    让 `reference_resolver` 等调用方不再直接内联硬编码错误；后续 P2 只需要
    替换 `get_retrieval_port()` 返回的实现，调用方无需改动。
    """

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


_default_port = UnavailableKnowledgeRetrievalService()


def get_retrieval_port() -> KnowledgeRetrievalPort:
    return _default_port
