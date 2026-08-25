from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from chat_sync.ai_models import ChatRun, RunStatus
from chat_sync.ai_services.run_service import RunService
from chat_sync.ai_services.pending_interaction_service import PendingInteractionService


@shared_task(name="chat_sync.ai_tasks.recovery_tasks.recover_chat_runs")
def recover_chat_runs():
    cutoff = timezone.now()
    recovered = 0
    for run in ChatRun.objects.filter(status=RunStatus.RUNNING, lease_expires_at__lt=cutoff).only("id", "first_token_at")[:100]:
        result = RunService.finalize_mock(
            run_id=run.id,
            status=RunStatus.INTERRUPTED if run.first_token_at else RunStatus.FAILED,
            error_code="run_lease_expired",
            error_message="run worker lease expired",
        )
        if result:
            recovered += 1
    return {"recovered": recovered}


@shared_task(name="chat_sync.ai_tasks.recovery_tasks.expire_chat_interactions")
def expire_chat_interactions():
    return PendingInteractionService.expire_due(limit=100)
