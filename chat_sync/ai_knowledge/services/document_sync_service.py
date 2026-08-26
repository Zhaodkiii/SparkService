from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import transaction
from django.utils import timezone

from chat_sync.ai_models.knowledge import (
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeDocumentScope,
    KnowledgeDocumentSource,
)

from .idempotency_service import IdempotencyConflict, IdempotencyService, compute_request_hash
from .knowledge_base_service import KnowledgeBaseService
from .payloads import document_to_payload

# D6：单文档正文上限，初始 1 MiB（UTF-8 字节数）。
MAX_CONTENT_BYTES = 1024 * 1024
MAX_TITLE_LENGTH = 255
DEFAULT_TITLE = "未命名文档"


class DocumentSyncError(Exception):
    """所有知识 Push 业务错误的基类；`code`/`status_code` 用于映射到工单第十章错误模型。"""

    code = "knowledge_document_invalid"
    status_code = 400

    def __init__(self, *, snapshot: dict[str, Any] | None = None):
        self.snapshot = snapshot
        super().__init__(self.code)


class DocumentPayloadInvalidError(DocumentSyncError):
    code = "knowledge_document_invalid"
    status_code = 400


class PayloadTooLargeError(DocumentSyncError):
    code = "knowledge_payload_too_large"
    status_code = 413


class KnowledgeBaseNotFoundError(DocumentSyncError):
    code = "knowledge_base_not_found"
    status_code = 404


class DocumentNotFoundError(DocumentSyncError):
    code = "knowledge_document_not_found"
    status_code = 404


class DocumentDeletedError(DocumentSyncError):
    code = "knowledge_document_deleted"
    status_code = 409


class RevisionConflictError(DocumentSyncError):
    code = "knowledge_revision_conflict"
    status_code = 409


class DocumentIdConflictError(DocumentSyncError):
    code = "knowledge_document_id_conflict"
    status_code = 409


class MutationIdempotencyConflictError(DocumentSyncError):
    code = "knowledge_idempotency_conflict"
    status_code = 409


class DocumentSyncService:
    """Push 主服务：每条 mutation 独立事务/保存点，单条失败不污染同批其它 mutation。"""

    @staticmethod
    def apply_mutation(*, user, mutation: dict[str, Any]) -> dict[str, Any]:
        mutation_id = mutation["mutation_id"]
        document_id = mutation["document_id"]
        operation = mutation["operation"]
        base_revision = mutation.get("base_revision")
        document_payload = mutation.get("document")

        request_hash = compute_request_hash(
            operation=operation,
            document_id=document_id,
            base_revision=base_revision,
            document=document_payload,
        )

        try:
            with transaction.atomic():
                replay = IdempotencyService.check_replay(user=user, mutation_id=mutation_id, request_hash=request_hash)
                if replay is not None:
                    snapshot = dict(replay.response_snapshot or {})
                    snapshot["replayed"] = True
                    return snapshot

                if operation == "create":
                    result = DocumentSyncService._apply_create(user=user, mutation=mutation)
                elif operation == "update":
                    result = DocumentSyncService._apply_update(user=user, mutation=mutation)
                elif operation == "delete":
                    result = DocumentSyncService._apply_delete(user=user, mutation=mutation)
                elif operation == "restore":
                    result = DocumentSyncService._apply_restore(user=user, mutation=mutation)
                else:
                    raise DocumentPayloadInvalidError()

                IdempotencyService.record(
                    user=user,
                    mutation_id=mutation_id,
                    document_id=document_id,
                    operation=operation,
                    request_hash=request_hash,
                    result_revision=int(result.get("revision") or 0),
                    response_snapshot=result,
                )
                return result
        except IdempotencyConflict as exc:
            raise MutationIdempotencyConflictError() from exc

    @staticmethod
    def _resolve_base(*, user, knowledge_base_id: Any) -> KnowledgeBase:
        # 未显式指定知识库时，Push 本身即可视为“首次访问”，幂等落地默认个人知识库
        # （工单 D5 建议 B/C 的幂等服务复用），避免客户端必须先调用 /default/ 才能同步文档。
        if not knowledge_base_id:
            return KnowledgeBaseService.get_or_create_default(user)
        base = KnowledgeBase.objects.filter(user=user, id=knowledge_base_id, is_deleted=False).first()
        if base is None:
            raise KnowledgeBaseNotFoundError()
        return base

    @staticmethod
    def _validate_document_fields(document_payload: dict[str, Any] | None) -> dict[str, Any]:
        document_payload = document_payload or {}
        title = str(document_payload.get("title") or "").strip()[:MAX_TITLE_LENGTH]
        content = str(document_payload.get("content") or "")
        if len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise PayloadTooLargeError()

        scope = document_payload.get("scope") or KnowledgeDocumentScope.PERSONAL
        if scope not in KnowledgeDocumentScope.values:
            raise DocumentPayloadInvalidError()

        source = document_payload.get("source") or KnowledgeDocumentSource.USER
        if source not in KnowledgeDocumentSource.values:
            raise DocumentPayloadInvalidError()

        excerpt = str(document_payload.get("excerpt") or "").strip()
        if not excerpt:
            excerpt = content.strip()[:200]

        return {
            "title": title or DEFAULT_TITLE,
            "content": content,
            "excerpt": excerpt,
            "scope": scope,
            "bound_model_id": document_payload.get("bound_model_id") or None,
            "source": source,
            "client_created_at": document_payload.get("client_created_at"),
            "client_updated_at": document_payload.get("client_updated_at"),
        }

    @staticmethod
    def _apply_create(*, user, mutation: dict[str, Any]) -> dict[str, Any]:
        document_id = mutation["document_id"]
        fields = DocumentSyncService._validate_document_fields(mutation.get("document"))
        content_hash = _content_hash(fields)

        existing = KnowledgeDocument.objects.select_for_update().filter(user=user, id=document_id).first()
        if existing is not None:
            if existing.content_hash == content_hash and not existing.is_deleted:
                return {**document_to_payload(existing), "status": "accepted", "replayed": True}
            raise DocumentIdConflictError(snapshot=document_to_payload(existing))

        base = DocumentSyncService._resolve_base(user=user, knowledge_base_id=mutation.get("knowledge_base_id"))
        device_hash = _hash_device_id((mutation.get("client") or {}).get("device_id"))
        document = KnowledgeDocument.objects.create(
            id=document_id,
            user=user,
            knowledge_base=base,
            revision=1,
            content_hash=content_hash,
            origin_device_id_hash=device_hash,
            last_device_id_hash=device_hash,
            **fields,
        )
        return {**document_to_payload(document), "status": "accepted", "replayed": False}

    @staticmethod
    def _apply_update(*, user, mutation: dict[str, Any]) -> dict[str, Any]:
        document_id = mutation["document_id"]
        base_revision = mutation.get("base_revision")
        document = KnowledgeDocument.objects.select_for_update().filter(user=user, id=document_id).first()
        if document is None:
            raise DocumentNotFoundError()
        if document.is_deleted:
            raise DocumentDeletedError(snapshot=document_to_payload(document))
        if document.revision != base_revision:
            raise RevisionConflictError(snapshot=document_to_payload(document))

        fields = DocumentSyncService._validate_document_fields(mutation.get("document"))
        content_hash = _content_hash(fields)
        if content_hash == document.content_hash:
            return {**document_to_payload(document), "status": "accepted", "replayed": True}

        for field, value in fields.items():
            setattr(document, field, value)
        document.content_hash = content_hash
        document.revision += 1
        device_hash = _hash_device_id((mutation.get("client") or {}).get("device_id"))
        if device_hash:
            document.last_device_id_hash = device_hash
        document.save()
        return {**document_to_payload(document), "status": "accepted", "replayed": False}

    @staticmethod
    def _apply_delete(*, user, mutation: dict[str, Any]) -> dict[str, Any]:
        document_id = mutation["document_id"]
        base_revision = mutation.get("base_revision")
        document = KnowledgeDocument.objects.select_for_update().filter(user=user, id=document_id).first()
        if document is None:
            raise DocumentNotFoundError()
        if document.is_deleted:
            return {**document_to_payload(document), "status": "accepted", "replayed": True}
        if document.revision != base_revision:
            raise RevisionConflictError(snapshot=document_to_payload(document))

        document.is_deleted = True
        document.deleted_at = timezone.now()
        document.revision += 1
        document.save()
        return {**document_to_payload(document), "status": "accepted", "replayed": False}

    @staticmethod
    def _apply_restore(*, user, mutation: dict[str, Any]) -> dict[str, Any]:
        document_id = mutation["document_id"]
        base_revision = mutation.get("base_revision")
        document = KnowledgeDocument.objects.select_for_update().filter(user=user, id=document_id).first()
        if document is None:
            raise DocumentNotFoundError()
        if not document.is_deleted:
            return {**document_to_payload(document), "status": "accepted", "replayed": True}
        if document.revision != base_revision:
            raise RevisionConflictError(snapshot=document_to_payload(document))

        document.is_deleted = False
        document.deleted_at = None
        document.revision += 1
        document.save()
        return {**document_to_payload(document), "status": "accepted", "replayed": False}


def _content_hash(fields: dict[str, Any]) -> str:
    canonical = {
        "title": fields["title"],
        "content": fields["content"],
        "scope": fields["scope"],
        "bound_model_id": fields.get("bound_model_id"),
    }
    raw = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _hash_device_id(device_id: Any) -> str | None:
    if not device_id:
        return None
    return hashlib.sha256(str(device_id).encode("utf-8")).hexdigest()
