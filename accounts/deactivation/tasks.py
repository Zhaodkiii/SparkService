import logging

from celery import shared_task

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
