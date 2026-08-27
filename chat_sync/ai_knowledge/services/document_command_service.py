from __future__ import annotations

import uuid
from typing import Any

from chat_sync.ai_knowledge.api.dto import document_to_dto
from chat_sync.ai_knowledge.errors import KnowledgeError
from chat_sync.ai_knowledge.services.document_sync_service import (
    DocumentDeletedError,
    DocumentNotFoundError,
    DocumentSyncService,
    KnowledgeBaseNotFoundError,
    RevisionConflictError,
)
from chat_sync.ai_knowledge.services.knowledge_base_service import KnowledgeBaseService
from chat_sync.ai_knowledge.services.payloads import decode_cursor, document_to_payload, encode_cursor
from chat_sync.ai_models.knowledge import KnowledgeDocument
from django.db.models import Q
from file_manager.models import ManagedFile


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
        document = KnowledgeDocument.objects.select_related("index_state").filter(user=user, id=document_id).first()
        if document is None or document.is_deleted:
            raise KnowledgeError("knowledge_document_not_found")
        return document

    @staticmethod
    def list_documents(*, user, base_id, cursor: str | None = None, limit: int = 20) -> dict[str, Any]:
        KnowledgeBaseService.get_owned(user, base_id)
        limit = max(1, min(int(limit or 20), 50))
        queryset = KnowledgeDocument.objects.select_related("index_state").filter(
            user=user, knowledge_base_id=base_id, is_deleted=False
        )
        cursor_dt, cursor_tie = decode_cursor(cursor)
        if cursor_dt is not None and cursor_tie is not None:
            queryset = queryset.filter(Q(server_updated_at__lt=cursor_dt) | Q(server_updated_at=cursor_dt, id__lt=cursor_tie))
        rows = list(queryset.order_by("-server_updated_at", "-id")[: limit + 1])
        page = rows[:limit]
        files = _files_for_documents(user, page)
        items = [document_to_dto(doc, include_content=False, file_record=files.get(str(doc.source_file_uuid))) for doc in page]
        last = page[-1] if page else None
        next_cursor = (
            encode_cursor(server_updated_at=last.server_updated_at, tie_breaker=str(last.id)) if last is not None and len(rows) > limit else None
        )
        return {"items": items, "next_cursor": next_cursor}

    @staticmethod
    def to_detail(document: KnowledgeDocument, user) -> dict[str, Any]:
        file_record = None
        if document.source_file_uuid:
            file_record = ManagedFile.objects.filter(user=user, file_uuid=document.source_file_uuid, is_deleted=False).first()
        return document_to_dto(document, include_content=True, file_record=file_record)


def _files_for_documents(user, documents: list[KnowledgeDocument]) -> dict[str, ManagedFile]:
    uuids = [doc.source_file_uuid for doc in documents if doc.source_file_uuid]
    if not uuids:
        return {}
    return {str(item.file_uuid): item for item in ManagedFile.objects.filter(user=user, file_uuid__in=uuids, is_deleted=False)}
