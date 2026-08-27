from __future__ import annotations

from celery import shared_task

from chat_sync.ai_knowledge.services.index_pipeline import index_document, rebuild_index_version


@shared_task(bind=True, max_retries=5, default_retry_delay=20, autoretry_for=(), ignore_result=True)
def index_document_task(self, document_id: str, revision: int):
    outcome = index_document(document_id, revision)
    if outcome == "failed" and self.request.retries < self.max_retries:
        raise self.retry(countdown=min(300, 20 * (2 ** self.request.retries)))
    return outcome


@shared_task(bind=True, max_retries=3, default_retry_delay=30, ignore_result=True)
def rebuild_index_version_task(self, version_id: str):
    return rebuild_index_version(version_id)


@shared_task(ignore_result=True)
def extract_document_task(document_id: str, revision: int):
    return index_document(document_id, revision)
