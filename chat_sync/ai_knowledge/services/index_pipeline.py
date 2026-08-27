from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from chat_sync.ai_knowledge.constants import CHUNKER_VERSION, MAX_CHUNKS_PER_BASE
from chat_sync.ai_knowledge.services.chunker import chunk_text
from chat_sync.ai_knowledge.services.extractors import ExtractionError, extract_text
from chat_sync.ai_models.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIndexState,
    KnowledgeIndexStatus,
    KnowledgeIndexVersion,
)
from chat_sync.ai_runtime.providers.embedding_gateway import EmbeddingGateway, resolve_embedding_route, vector_norm
from chat_sync.ai_runtime.providers.exceptions import LLMError
from file_manager.models import ManagedFile

logger = logging.getLogger("chat_sync.ai.knowledge")


def index_document(document_id: str, expected_revision: int) -> str:
    document = KnowledgeDocument.objects.select_related("knowledge_base").filter(id=document_id).first()
    if document is None or document.is_deleted:
        return "deleted"
    if document.revision != expected_revision:
        return "superseded"
    state, _ = KnowledgeIndexState.objects.get_or_create(document=document)
    state.status = KnowledgeIndexStatus.PROCESSING
    state.save(update_fields=["status", "updated_at"])

    try:
        content = document.content
        if document.source_file_uuid and not content.strip():
            content = _load_file_text(document)
            if content and content != document.content:
                document.content = content
                document.excerpt = content.strip()[:200]
                document.save(update_fields=["content", "excerpt", "server_updated_at"])
                if document.revision != expected_revision:
                    return "superseded"

        pieces = chunk_text(content)
        existing_base_chunks = KnowledgeChunk.objects.filter(document__knowledge_base_id=document.knowledge_base_id).exclude(document_id=document.id).count()
        if existing_base_chunks + len(pieces) > MAX_CHUNKS_PER_BASE:
            raise ValueError("knowledge_file_too_large")

        vectors: list[list[float]] = []
        provider = ""
        model = ""
        dimension = None
        if pieces:
            try:
                route = resolve_embedding_route()
                provider = route.provider
                model = route.model
                vectors = EmbeddingGateway(route).embed([item["content"] for item in pieces])
                dimension = len(vectors[0]) if vectors else None
            except LLMError as exc:
                logger.warning("knowledge.embed.unavailable document_id=%s error=%s", document_id, exc)
                vectors = [[] for _ in pieces]

        signature = hashlib.sha256(f"{CHUNKER_VERSION}:{model}:{document.content_hash}".encode()).hexdigest()[:24]
        with transaction.atomic():
            document.refresh_from_db()
            if document.revision != expected_revision:
                return "superseded"
            KnowledgeChunk.objects.filter(document=document).exclude(document_revision=document.revision).delete()
            KnowledgeChunk.objects.filter(document=document, document_revision=document.revision).delete()
            for index, piece in enumerate(pieces):
                embedding = vectors[index] if index < len(vectors) else []
                KnowledgeChunk.objects.create(
                    document=document,
                    document_revision=document.revision,
                    sequence=piece["sequence"],
                    content=piece["content"],
                    content_hash=piece["content_hash"],
                    token_count=piece["token_count"],
                    embedding=embedding,
                    embedding_norm=vector_norm(embedding) if embedding else None,
                    metadata={"chunker_version": CHUNKER_VERSION},
                )
            state.document_revision = document.revision
            state.status = KnowledgeIndexStatus.READY
            state.chunk_count = len(pieces)
            state.embedding_provider = provider
            state.embedding_model = model
            state.embedding_dimension = dimension
            state.embedding_signature = signature
            state.index_version = signature
            state.last_error_code = None
            state.error_message = ""
            state.indexed_at = timezone.now()
            state.attempt_count = (state.attempt_count or 0) + 1
            state.save()
        return "ready"
    except ExtractionError as exc:
        _fail(state, exc.code, str(exc))
        return "failed"
    except Exception as exc:
        logger.exception("knowledge.index.failed document_id=%s", document_id)
        _fail(state, "knowledge_index_unavailable", str(exc)[:200])
        return "failed"


def rebuild_index_version(version_id: str) -> str:
    version = KnowledgeIndexVersion.objects.select_related("knowledge_base").filter(id=version_id).first()
    if version is None:
        return "missing"
    version.status = KnowledgeIndexStatus.PROCESSING
    version.started_at = timezone.now()
    version.save(update_fields=["status", "started_at"])
    documents = list(
        KnowledgeDocument.objects.filter(knowledge_base=version.knowledge_base, is_deleted=False)
    )
    outcomes = [index_document(str(document.id), document.revision) for document in documents]
    chunk_count = KnowledgeChunk.objects.filter(document__knowledge_base=version.knowledge_base, document__is_deleted=False).count()
    failed = any(item == "failed" for item in outcomes)
    with transaction.atomic():
        version.document_count = len(documents)
        version.chunk_count = chunk_count
        version.status = KnowledgeIndexStatus.FAILED if failed else KnowledgeIndexStatus.READY
        version.completed_at = timezone.now()
        version.signature = f"idx_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
        if not failed:
            KnowledgeIndexVersion.objects.filter(knowledge_base=version.knowledge_base, is_active=True).exclude(pk=version.pk).update(is_active=False)
            version.is_active = True
        version.save()
    return version.status


def _load_file_text(document: KnowledgeDocument) -> str:
    file_record = ManagedFile.objects.filter(file_uuid=document.source_file_uuid, user=document.user, is_deleted=False).first()
    if file_record is None:
        raise ExtractionError("knowledge_file_not_found")
    payload = _read_file_bytes(file_record)
    return extract_text(file_name=file_record.original_name, mime_type=file_record.mime_type, payload=payload)


def _read_file_bytes(file_record: ManagedFile) -> bytes:
    path = (file_record.file_path or "").strip()
    if path and not path.startswith("http://") and not path.startswith("https://"):
        try:
            with open(path, "rb") as handle:
                return handle.read()
        except OSError as exc:
            raise ExtractionError("knowledge_file_unsupported", "cannot read local file") from exc
    raise ExtractionError("knowledge_file_unsupported", "remote file extract is not configured")


def _fail(state: KnowledgeIndexState, code: str, message: str) -> None:
    state.status = KnowledgeIndexStatus.FAILED
    state.last_error_code = code
    state.error_message = message[:512]
    state.attempt_count = (state.attempt_count or 0) + 1
    state.save(update_fields=["status", "last_error_code", "error_message", "attempt_count", "updated_at"])
