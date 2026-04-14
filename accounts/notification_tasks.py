import logging

from celery import shared_task

from accounts.models import NotificationCampaign
from accounts.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_notification_campaign_task(self, campaign_id: int, request_id: str = ""):
    logger.info(
        "send_notification_campaign_task start campaign_id=%s request_id=%s task_id=%s",
        campaign_id,
        request_id,
        self.request.id,
    )
    try:
        result = NotificationService.execute_campaign(
            campaign_id=campaign_id,
            request_id=request_id or "",
            task_id=self.request.id,
        )
        logger.info(
            "send_notification_campaign_task done campaign_id=%s status=%s success=%s failure=%s",
            campaign_id,
            result.get("status"),
            result.get("success_count"),
            result.get("failure_count"),
        )
        return result
    except Exception as exc:
        retries = int(getattr(self.request, "retries", 0))
        max_retries = int(getattr(self, "max_retries", 0))
        logger.exception(
            "send_notification_campaign_task failed campaign_id=%s request_id=%s task_id=%s retries=%s max_retries=%s",
            campaign_id,
            request_id,
            self.request.id,
            retries,
            max_retries,
        )
        if retries >= max_retries:
            NotificationCampaign.objects.filter(id=campaign_id).update(
                status=NotificationCampaign.Status.FAILED,
                error_message=str(exc)[:2000],
            )
        raise
