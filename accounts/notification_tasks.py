import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=0,
)
def send_notification_campaign_task(self, campaign_id: int, request_id: str = ""):
    logger.warning(
        "legacy send_notification_campaign_task discarded campaign_id=%s request_id=%s task_id=%s",
        campaign_id,
        request_id,
        self.request.id,
    )
    return {"status": "discarded_legacy_task", "campaign_id": campaign_id}
