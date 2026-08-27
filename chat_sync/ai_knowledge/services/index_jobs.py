from __future__ import annotations

from django.utils import timezone

from chat_sync.ai_models.knowledge import KnowledgeDocument, KnowledgeIndexState, KnowledgeIndexStatus


def mark_document_pending(document: KnowledgeDocument, *, status: str = KnowledgeIndexStatus.PENDING) -> KnowledgeIndexState:
    state, _ = KnowledgeIndexState.objects.get_or_create(document=document)
    if state.document_revision == document.revision and state.status == KnowledgeIndexStatus.READY:
        status = KnowledgeIndexStatus.STALE
    state.status = status
    state.last_error_code = None
    state.error_message = ""
    state.save(update_fields=["status", "last_error_code", "error_message", "updated_at"])
    return state


def enqueue_document_index(document: KnowledgeDocument) -> None:
    mark_document_pending(document)
    try:
        from chat_sync.ai_tasks.knowledge_tasks import index_document_task

        index_document_task.delay(str(document.id), int(document.revision))
    except Exception:
        logger = __import__("logging").getLogger("chat_sync.ai.knowledge")
        logger.warning("knowledge.index.enqueue_failed document_id=%s", document.id)


def enqueue_base_rebuild(base_id: str) -> str:
    from chat_sync.ai_knowledge.errors import KnowledgeError
    from chat_sync.ai_models.knowledge import KnowledgeIndexStatus, KnowledgeIndexVersion

    running = KnowledgeIndexVersion.objects.filter(
        knowledge_base_id=base_id,
        status__in=[KnowledgeIndexStatus.PENDING, KnowledgeIndexStatus.PROCESSING],
    ).first()
    if running is not None:
        raise KnowledgeError("knowledge_index_job_already_running", details={"job_id": str(running.id)})
    version = KnowledgeIndexVersion.objects.create(
        knowledge_base_id=base_id,
        status=KnowledgeIndexStatus.PENDING,
        started_at=timezone.now(),
    )
    from chat_sync.ai_tasks.knowledge_tasks import rebuild_index_version_task

    rebuild_index_version_task.delay(str(version.id))
    return str(version.id)
