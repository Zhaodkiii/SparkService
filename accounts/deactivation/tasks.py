import logging
from datetime import timedelta

from celery import shared_task
from django.core.files.storage import default_storage
from django.utils import timezone

from accounts.models import AccountDeactivation
from accounts.services.deactivation_service import DeactivationService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def process_deactivation_task(self, deactivation_id: int, request_id: str):
    logger.info("process_deactivation_task start deactivation_id=%s request_id=%s task_id=%s", deactivation_id, request_id, self.request.id)
    try:
        result = DeactivationService.process_deactivation(
            deactivation_id=deactivation_id,
            request_id=request_id or "",
            task_id=self.request.id,
        )
        logger.info("process_deactivation_task done deactivation_id=%s state=%s", result.get("deactivation_id"), result.get("state"))
        return result
    except Exception as exc:
        retries = int(getattr(self.request, "retries", 0))
        max_retries = int(getattr(self, "max_retries", 0))
        logger.exception(
            "process_deactivation_task failed deactivation_id=%s request_id=%s task_id=%s retries=%s max_retries=%s",
            deactivation_id,
            request_id,
            self.request.id,
            retries,
            max_retries,
        )
        # Mark as failed only when this is the final retry attempt.
        if retries >= max_retries:
            DeactivationService.mark_failed(
                deactivation_id=deactivation_id,
                request_id=request_id or "",
                error_message=str(exc),
            )
        raise


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def schedule_deactivation_processing_task(self, limit: int = 50):
    now = timezone.now()
    rows = list(
        AccountDeactivation.objects.filter(
            state=AccountDeactivation.DeactivationState.SCHEDULED,
            scheduled_at__lte=now,
        )
        .order_by("scheduled_at", "id")
        .values_list("id", "request_id")[:limit]
    )
    task_ids = []
    for deactivation_id, request_id in rows:
        result = process_deactivation_task.delay(deactivation_id, request_id or "")
        task_ids.append(result.id)
    return {"status": "success", "scheduled_count": len(rows), "task_ids": task_ids}


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def cleanup_deactivation_backups_task(self, limit: int = 100):
    now = timezone.now()
    rows = list(
        AccountDeactivation.objects.filter(
            state=AccountDeactivation.DeactivationState.COMPLETED,
            backup_expires_at__isnull=False,
            backup_expires_at__lte=now,
        )
        .exclude(backup_uri="")
        .order_by("backup_expires_at", "id")[:limit]
    )
    cleaned = 0
    for row in rows:
        try:
            if default_storage.exists(row.backup_uri):
                default_storage.delete(row.backup_uri)
            row.backup_uri = ""
            row.backup_checksum = ""
            row.save(update_fields=["backup_uri", "backup_checksum"])
            cleaned += 1
        except Exception:
            logger.exception("cleanup_deactivation_backups_task failed row_id=%s", row.id)
    return {"status": "success", "cleaned_count": cleaned}


@shared_task
def deactivation_health_check_task():
    cutoff = timezone.now() - timedelta(hours=24)
    stuck_count = AccountDeactivation.objects.filter(
        state__in=[
            AccountDeactivation.DeactivationState.DATA_BACKED_UP,
            AccountDeactivation.DeactivationState.ANONYMIZED,
            AccountDeactivation.DeactivationState.RELATED_DATA_DELETED,
            AccountDeactivation.DeactivationState.ACCOUNT_DISABLED,
        ],
        processed_at__lt=cutoff,
    ).count()
    stats = {
        state: AccountDeactivation.objects.filter(state=state).count()
        for state, _label in AccountDeactivation.DeactivationState.choices
    }
    return {
        "status": "healthy" if stuck_count == 0 else "warning",
        "stuck_count": stuck_count,
        "stats": stats,
        "timestamp": timezone.now().isoformat(),
    }
