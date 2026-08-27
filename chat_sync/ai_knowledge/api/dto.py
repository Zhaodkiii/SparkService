from __future__ import annotations

from typing import Any

from chat_sync.ai_models.knowledge import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIndexState,
    KnowledgeIndexStatus,
    KnowledgeIndexVersion,
)
from file_manager.models import ManagedFile
from file_manager.url_utils import managed_file_download_url


def iso(value) -> str | None:
    return value.isoformat() if value else None


def sanitize_retrieval_config(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    top_k = data.get("top_k", 6)
    try:
        top_k = int(top_k)
    except (TypeError, ValueError):
        top_k = 6
    top_k = max(1, min(top_k, 20))
    threshold = data.get("score_threshold", 0.72)
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        threshold = 0.72
    threshold = max(0.0, min(threshold, 1.0))
    return {
        "top_k": top_k,
        "score_threshold": round(threshold, 4),
        "rerank_enabled": bool(data.get("rerank_enabled", False)),
    }


def index_state_to_dto(state: KnowledgeIndexState | None) -> dict[str, Any]:
    if state is None:
        return {
            "status": KnowledgeIndexStatus.PENDING,
            "indexed_revision": 0,
            "chunk_count": 0,
            "index_version": None,
            "error_code": None,
            "error_message": "",
            "indexed_at": None,
        }
    return {
        "status": state.status,
        "indexed_revision": state.document_revision,
        "chunk_count": state.chunk_count,
        "index_version": state.index_version or None,
        "error_code": state.last_error_code,
        "error_message": state.error_message or "",
        "indexed_at": iso(state.indexed_at),
    }


def source_file_summary(file_record: ManagedFile | None) -> dict[str, Any] | None:
    if file_record is None:
        return None
    return {
        "file_uuid": str(file_record.file_uuid),
        "name": file_record.original_name,
        "mime_type": file_record.mime_type,
        "size": file_record.file_size,
        "preview_url": managed_file_download_url(file_record) or None,
    }


def document_to_dto(
    document: KnowledgeDocument,
    *,
    include_content: bool = False,
    file_record: ManagedFile | None = None,
) -> dict[str, Any]:
    state = getattr(document, "index_state", None)
    payload: dict[str, Any] = {
        "id": str(document.id),
        "knowledge_base_id": str(document.knowledge_base_id),
        "revision": document.revision,
        "title": document.title,
        "excerpt": document.excerpt,
        "source": document.source,
        "scope": document.scope,
        "bound_model_id": document.bound_model_id,
        "source_file": source_file_summary(file_record),
        "content_hash": document.content_hash,
        "is_deleted": document.is_deleted,
        "deleted_at": iso(document.deleted_at),
        "index_state": index_state_to_dto(state),
        "created_at": iso(document.created_at),
        "server_updated_at": iso(document.server_updated_at),
    }
    if include_content:
        payload["content"] = document.content
    return payload


def base_permissions(base: KnowledgeBase) -> dict[str, bool]:
    return {
        "can_edit": not base.is_deleted,
        "can_delete": (not base.is_deleted) and (not base.is_default),
        "can_reindex": not base.is_deleted,
    }


def knowledge_base_summary(
    base: KnowledgeBase,
    *,
    document_count: int = 0,
    file_count: int = 0,
    index_status: str = KnowledgeIndexStatus.PENDING,
    active_index_version: str | None = None,
    sync_status: str = "synced",
) -> dict[str, Any]:
    return {
        "id": str(base.id),
        "name": base.name,
        "kind": base.kind,
        "is_default": base.is_default,
        "revision": base.revision,
        "document_count": document_count,
        "file_count": file_count,
        "index_status": index_status,
        "active_index_version": active_index_version,
        "sync_status": sync_status,
        "server_updated_at": iso(base.server_updated_at),
    }


def knowledge_base_detail(
    base: KnowledgeBase,
    *,
    document_count: int = 0,
    file_count: int = 0,
    index_status: str = KnowledgeIndexStatus.PENDING,
    active_index_version: str | None = None,
    latest_index: dict[str, Any] | None = None,
    documents_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = knowledge_base_summary(
        base,
        document_count=document_count,
        file_count=file_count,
        index_status=index_status,
        active_index_version=active_index_version,
    )
    return {
        **summary,
        "created_at": iso(base.created_at),
        "is_deleted": base.is_deleted,
        "retrieval_config": sanitize_retrieval_config(base.retrieval_config),
        "documents_summary": documents_summary or {"ready": 0, "pending": document_count, "failed": 0},
        "latest_index": latest_index,
        "permissions": base_permissions(base),
    }


def index_version_to_dto(version: KnowledgeIndexVersion) -> dict[str, Any]:
    return {
        "id": str(version.id),
        "knowledge_base_id": str(version.knowledge_base_id),
        "status": version.status,
        "is_active": version.is_active,
        "signature": version.signature or None,
        "document_count": version.document_count,
        "chunk_count": version.chunk_count,
        "embedding_provider": version.embedding_provider or None,
        "embedding_model": version.embedding_model or None,
        "dimension": version.embedding_dimension,
        "chunker_version": version.chunker_version,
        "started_at": iso(version.started_at),
        "completed_at": iso(version.completed_at),
        "error_code": version.error_code or None,
        "error_message": version.error_message or "",
    }


def citation_to_dto(
    *,
    citation_id: str,
    knowledge_base_id: str,
    knowledge_base_name: str,
    document_id: str,
    document_title: str,
    chunk_id: str,
    chunk_revision: int,
    index_version: str | None,
    snippet: str,
    relevance: str,
) -> dict[str, Any]:
    return {
        "citation_id": citation_id,
        "knowledge_base_id": knowledge_base_id,
        "knowledge_base_name": knowledge_base_name,
        "document_id": document_id,
        "document_title": document_title,
        "chunk_id": chunk_id,
        "chunk_revision": chunk_revision,
        "index_version": index_version,
        "snippet": snippet[:400],
        "relevance": relevance,
    }


def relevance_label(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.7:
        return "medium"
    return "low"


def chunk_to_resolved(chunk: KnowledgeChunk, *, title: str, index_version: str = "") -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.id),
        "document_id": str(chunk.document_id),
        "document_revision": chunk.document_revision,
        "title": title,
        "content": chunk.content,
        "content_hash": chunk.content_hash,
        "index_version": index_version,
        "metadata": chunk.metadata or {},
    }
