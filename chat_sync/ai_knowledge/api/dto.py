from __future__ import annotations

from typing import Any

from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeDocument


def iso(value) -> str | None:
    return value.isoformat() if value else None


def document_to_dto(document: KnowledgeDocument, *, include_content: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(document.id),
        "knowledge_base_id": str(document.knowledge_base_id),
        "revision": document.revision,
        "title": document.title,
        "excerpt": document.excerpt,
        "source": document.source,
        "scope": document.scope,
        "bound_model_id": document.bound_model_id,
        "content_hash": document.content_hash,
        "is_deleted": document.is_deleted,
        "deleted_at": iso(document.deleted_at),
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
    }


def knowledge_base_summary(
    base: KnowledgeBase,
    *,
    document_count: int = 0,
    sync_status: str = "synced",
) -> dict[str, Any]:
    return {
        "id": str(base.id),
        "name": base.name,
        "kind": base.kind,
        "is_default": base.is_default,
        "revision": base.revision,
        "document_count": document_count,
        "sync_status": sync_status,
        "server_updated_at": iso(base.server_updated_at),
    }


def knowledge_base_detail(
    base: KnowledgeBase,
    *,
    document_count: int = 0,
) -> dict[str, Any]:
    summary = knowledge_base_summary(base, document_count=document_count)
    return {
        **summary,
        "created_at": iso(base.created_at),
        "is_deleted": base.is_deleted,
        "permissions": base_permissions(base),
    }
