from __future__ import annotations

from typing import Any

from chat_sync.ai_knowledge.retrieval.port import KnowledgeRetrievalUnavailable, ResolvedKnowledgeChunk
from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeIndexStatus
from chat_sync.ai_runtime.providers.embedding_gateway import cosine_similarity, EmbeddingGateway, resolve_embedding_route, vector_norm
from chat_sync.ai_runtime.providers.exceptions import LLMError


class NativeVectorRetrievalService:
    def resolve_chunk(self, *, user, chunk_id: str, revision: int | None = None) -> ResolvedKnowledgeChunk:
        chunk = (
            KnowledgeChunk.objects.select_related("document", "document__knowledge_base")
            .filter(id=chunk_id, document__user=user, document__is_deleted=False, document__knowledge_base__is_deleted=False)
            .first()
        )
        if chunk is None:
            raise KnowledgeRetrievalUnavailable("knowledge_document_not_found")
        if revision is not None and chunk.document_revision != revision:
            raise KnowledgeRetrievalUnavailable("knowledge_document_revision_conflict")
        return _to_resolved(chunk)

    def search(
        self,
        *,
        user,
        base_ids: list[str],
        query: str,
        top_k: int = 8,
        threshold: float = 0.75,
    ) -> list[ResolvedKnowledgeChunk]:
        owned_ids = list(
            KnowledgeBase.objects.filter(user=user, is_deleted=False, id__in=base_ids).values_list("id", flat=True)
        )
        if not owned_ids or not (query or "").strip():
            return []
        chunks = list(
            KnowledgeChunk.objects.select_related("document", "document__knowledge_base", "document__index_state")
            .filter(
                document__user=user,
                document__is_deleted=False,
                document__knowledge_base_id__in=owned_ids,
                document__index_state__status=KnowledgeIndexStatus.READY,
            )
        )
        if not chunks:
            return []
        query_vector = _embed_query(query)
        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk in chunks:
            if query_vector and chunk.embedding:
                score = cosine_similarity(query_vector, chunk.embedding, vector_norm(query_vector), chunk.embedding_norm)
            else:
                score = _lexical_score(query, chunk.content)
            if score >= threshold:
                scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, chunk in scored[: max(1, min(int(top_k or 8), 20))]:
            resolved = _to_resolved(chunk)
            resolved.metadata["score"] = round(score, 4)
            results.append(resolved)
        return results


def _embed_query(query: str) -> list[float]:
    try:
        route = resolve_embedding_route()
        vectors = EmbeddingGateway(route).embed([query])
        return vectors[0] if vectors else []
    except LLMError:
        return []


def _lexical_score(query: str, content: str) -> float:
    tokens = [item for item in query.lower().split() if item]
    if not tokens:
        return 0.0
    haystack = (content or "").lower()
    hits = sum(1 for token in tokens if token in haystack)
    return hits / len(tokens)


def _to_resolved(chunk: KnowledgeChunk) -> ResolvedKnowledgeChunk:
    document = chunk.document
    base = document.knowledge_base
    index_version = ""
    state = getattr(document, "index_state", None)
    if state is not None:
        index_version = state.index_version or ""
    return ResolvedKnowledgeChunk(
        chunk_id=str(chunk.id),
        document_id=str(document.id),
        document_revision=chunk.document_revision,
        title=document.title,
        content=chunk.content,
        content_hash=chunk.content_hash,
        index_version=index_version,
        metadata={
            "knowledge_base_id": str(base.id),
            "knowledge_base_name": base.name,
            "document_revision": document.revision,
        },
    )
