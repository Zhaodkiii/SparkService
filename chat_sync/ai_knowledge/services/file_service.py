from __future__ import annotations

import uuid
from pathlib import Path

from chat_sync.ai_knowledge.constants import (
    KNOWLEDGE_FILE_BUSINESS_TYPE,
    MAX_FILE_BYTES,
    SUPPORTED_FILE_EXTS,
    SUPPORTED_MIME_TYPES,
)
from chat_sync.ai_knowledge.errors import KnowledgeError
from chat_sync.ai_knowledge.services.document_command_service import DocumentCommandService
from chat_sync.ai_knowledge.services.index_jobs import enqueue_document_index
from chat_sync.ai_knowledge.services.knowledge_base_service import KnowledgeBaseService
from chat_sync.ai_models.knowledge import KnowledgeDocument, KnowledgeDocumentSource
from file_manager.business_relations import bind_file_to_business
from file_manager.models import ManagedFile, ManagedFileBusinessRelation
from file_manager.url_utils import managed_file_download_url


class KnowledgeFileService:
    @staticmethod
    def list_files(*, user, base_id) -> dict:
        KnowledgeBaseService.get_owned(user, base_id)
        relations = (
            ManagedFileBusinessRelation.objects.select_related("file")
            .filter(user=user, business_type=KNOWLEDGE_FILE_BUSINESS_TYPE, business_id=str(base_id), file__is_deleted=False)
            .order_by("-created_at")
        )
        items = []
        for relation in relations:
            file_record = relation.file
            document = KnowledgeDocument.objects.select_related("index_state").filter(
                user=user, knowledge_base_id=base_id, source_file_uuid=file_record.file_uuid, is_deleted=False
            ).first()
            index_state = getattr(document, "index_state", None) if document else None
            items.append(
                {
                    "file_uuid": str(file_record.file_uuid),
                    "name": file_record.original_name,
                    "mime_type": file_record.mime_type,
                    "size": file_record.file_size,
                    "preview_url": managed_file_download_url(file_record) or None,
                    "document_id": str(document.id) if document else None,
                    "processing_status": index_state.status if index_state else "uploaded",
                    "error_code": index_state.last_error_code if index_state else None,
                }
            )
        return {"items": items}

    @staticmethod
    def bind(*, user, base_id, file_uuid, reuse: bool = False) -> dict:
        base = KnowledgeBaseService.get_owned(user, base_id)
        file_record = ManagedFile.objects.filter(user=user, file_uuid=file_uuid, is_deleted=False).first()
        if file_record is None:
            raise KnowledgeError("knowledge_file_not_found")
        _validate_file(file_record)
        existing = KnowledgeDocument.objects.filter(
            user=user, knowledge_base=base, source_file_uuid=file_record.file_uuid, is_deleted=False
        ).first()
        if existing is not None:
            if reuse:
                return {"reused": True, "document_id": str(existing.id)}
            raise KnowledgeError("knowledge_file_duplicate", details={"document_id": str(existing.id)})
        if file_record.file_md5:
            hash_match = KnowledgeDocument.objects.filter(
                user=user, knowledge_base=base, is_deleted=False, source_file_uuid__isnull=False
            )
            related_files = ManagedFile.objects.filter(user=user, file_md5=file_record.file_md5, is_deleted=False).exclude(pk=file_record.pk)
            if related_files.exists() and not reuse:
                existing_doc = KnowledgeDocument.objects.filter(
                    user=user, knowledge_base=base, source_file_uuid__in=list(related_files.values_list("file_uuid", flat=True)), is_deleted=False
                ).first()
                if existing_doc is not None:
                    raise KnowledgeError("knowledge_file_duplicate", details={"document_id": str(existing_doc.id)})
        bind_file_to_business(user, file_record, KNOWLEDGE_FILE_BUSINESS_TYPE, str(base.id))
        document = DocumentCommandService.create(
            user=user,
            base_id=base.id,
            title=file_record.original_name or "导入文档",
            content="",
            source=KnowledgeDocumentSource.IMPORT,
            document_id=uuid.uuid4(),
        )
        document.source_file_uuid = file_record.file_uuid
        document.save(update_fields=["source_file_uuid", "server_updated_at"])
        enqueue_document_index(document)
        return {"reused": False, "document_id": str(document.id), "file_uuid": str(file_record.file_uuid)}

    @staticmethod
    def unbind(*, user, base_id, file_uuid, delete_document: bool = True) -> None:
        KnowledgeBaseService.get_owned(user, base_id)
        ManagedFileBusinessRelation.objects.filter(
            user=user, business_type=KNOWLEDGE_FILE_BUSINESS_TYPE, business_id=str(base_id), file__file_uuid=file_uuid
        ).delete()
        if delete_document:
            document = KnowledgeDocument.objects.filter(user=user, knowledge_base_id=base_id, source_file_uuid=file_uuid, is_deleted=False).first()
            if document is not None:
                DocumentCommandService.delete(user=user, document_id=document.id, revision=document.revision)


def _validate_file(file_record: ManagedFile) -> None:
    ext = Path(file_record.original_name or "").suffix.lower()
    mime = (file_record.mime_type or "").lower()
    if ext not in SUPPORTED_FILE_EXTS and mime not in SUPPORTED_MIME_TYPES:
        raise KnowledgeError("knowledge_file_unsupported")
    if file_record.file_size and file_record.file_size > MAX_FILE_BYTES:
        raise KnowledgeError("knowledge_file_too_large", details={"max_bytes": MAX_FILE_BYTES})
