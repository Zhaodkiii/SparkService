from __future__ import annotations

import uuid
from typing import Any

from chat_sync.ai_knowledge.api.dto import document_to_dto
from chat_sync.ai_knowledge.errors import KnowledgeError
from chat_sync.ai_knowledge.services.document_sync_service import (
    DocumentDeletedError,
    DocumentNotFoundError,
    DocumentSyncService,
    RevisionConflictError,
)
from chat_sync.ai_knowledge.services.knowledge_base_service import KnowledgeBaseService
from chat_sync.ai_knowledge.services.payloads import decode_cursor, encode_cursor
from chat_sync.ai_models.knowledge import KnowledgeDocument
from django.db.models import Q


class DocumentCommandService:
    """Web 文档 CRUD 与同步 mutation 共用 DocumentSyncService 写入规则。"""

    @staticmethod
    def create(*, user, base_id, title: str, content: str, scope: str = "personal", source: str = "user", document_id=None) -> KnowledgeDocument:
        KnowledgeBaseService.get_owned(user, base_id)
        resolved_id = document_id or uuid.uuid4()
        DocumentSyncService.apply_mutation(
            user=user,
            mutation={
                "mutation_id": uuid.uuid4(),
                "document_id": resolved_id,
                "operation": "create",
                "knowledge_base_id": base_id,
                "document": {"title": title, "content": content, "scope": scope, "source": source},
            },
        )
        return KnowledgeDocument.objects.get(user=user, id=resolved_id)

    @staticmethod
    def update(*, user, document_id, revision: int, title: str | None = None, content: str | None = None) -> KnowledgeDocument:
        document = KnowledgeDocument.objects.filter(user=user, id=document_id).first()
        if document is None:
            raise KnowledgeError("knowledge_document_not_found")
        payload = {
            "title": title if title is not None else document.title,
            "content": content if content is not None else document.content,
            "scope": document.scope,
            "source": document.source,
        }
        try:
            DocumentSyncService.apply_mutation(
                user=user,
                mutation={
                    "mutation_id": uuid.uuid4(),
                    "document_id": document_id,
                    "operation": "update",
                    "base_revision": revision,
                    "document": payload,
                },
            )
        except RevisionConflictError as exc:
            raise KnowledgeError(
                "knowledge_document_revision_conflict",
                details={"resource_id": str(document_id), "server_revision": (exc.snapshot or {}).get("revision")},
            ) from exc
        except DocumentDeletedError as exc:
            raise KnowledgeError("knowledge_document_deleted", details={"resource_id": str(document_id)}) from exc
        except DocumentNotFoundError as exc:
            raise KnowledgeError("knowledge_document_not_found") from exc
        return KnowledgeDocument.objects.get(user=user, id=document_id)

    @staticmethod
    def delete(*, user, document_id, revision: int | None) -> KnowledgeDocument:
        document = KnowledgeDocument.objects.filter(user=user, id=document_id).first()
        if document is None:
            raise KnowledgeError("knowledge_document_not_found")
        try:
            DocumentSyncService.apply_mutation(
                user=user,
                mutation={
                    "mutation_id": uuid.uuid4(),
                    "document_id": document_id,
                    "operation": "delete",
                    "base_revision": revision if revision is not None else document.revision,
                },
            )
        except RevisionConflictError as exc:
            raise KnowledgeError(
                "knowledge_document_revision_conflict",
                details={"resource_id": str(document_id), "server_revision": (exc.snapshot or {}).get("revision")},
            ) from exc
        except DocumentNotFoundError as exc:
            raise KnowledgeError("knowledge_document_not_found") from exc
        return KnowledgeDocument.objects.get(user=user, id=document_id)

    @staticmethod
    def get(*, user, document_id) -> KnowledgeDocument:
        document = KnowledgeDocument.objects.filter(user=user, id=document_id).first()
        if document is None or document.is_deleted:
            raise KnowledgeError("knowledge_document_not_found")
        return document

    @staticmethod
    def list_documents(*, user, base_id, cursor: str | None = None, limit: int = 20, q: str = "") -> dict[str, Any]:
        KnowledgeBaseService.get_owned(user, base_id)
        limit = max(1, min(int(limit or 20), 50))
        queryset = KnowledgeDocument.objects.filter(user=user, knowledge_base_id=base_id, is_deleted=False)
        if q:
            query = q.strip()[:64]
            queryset = queryset.filter(Q(title__icontains=query) | Q(content__icontains=query))
        cursor_dt, cursor_tie = decode_cursor(cursor)
        if cursor_dt is not None and cursor_tie is not None:
            queryset = queryset.filter(Q(server_updated_at__lt=cursor_dt) | Q(server_updated_at=cursor_dt, id__lt=cursor_tie))
        rows = list(queryset.order_by("-server_updated_at", "-id")[: limit + 1])
        page = rows[:limit]
        items = [document_to_dto(doc, include_content=False) for doc in page]
        last = page[-1] if page else None
        next_cursor = (
            encode_cursor(server_updated_at=last.server_updated_at, tie_breaker=str(last.id)) if last is not None and len(rows) > limit else None
        )
        return {"items": items, "next_cursor": next_cursor}

    @staticmethod
    def to_detail(document: KnowledgeDocument, user) -> dict[str, Any]:
        return document_to_dto(document, include_content=True)
