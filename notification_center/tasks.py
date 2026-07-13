from __future__ import annotations

import logging

from celery import shared_task
from django.db import models, transaction
from django.utils import timezone

from notification_center.models import NotificationOutbox
from notification_center.services import NotificationCenterService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def execute_notification_campaign_task(self, campaign_id: int, request_id: str = ""):
    logger.info(
        "execute_notification_campaign_task start campaign_id=%s request_id=%s task_id=%s",
        campaign_id,
        request_id,
        self.request.id,
    )
    result = NotificationCenterService.execute_campaign(
        campaign_id=campaign_id,
        request_id=request_id or "",
        task_id=self.request.id,
    )
    logger.info(
        "execute_notification_campaign_task done campaign_id=%s status=%s success=%s failure=%s",
        campaign_id,
        result.get("status"),
        result.get("success_count"),
        result.get("failure_count"),
    )
    return result


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def execute_sms_otp_intent_task(self, intent_id: int, message_id: int):
    return NotificationCenterService.execute_phone_otp_intent(
        intent_id=intent_id,
        message_id=message_id,
        task_id=self.request.id,
    )


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def execute_email_otp_intent_task(self, intent_id: int, message_id: int):
    return NotificationCenterService.execute_email_otp_intent(
        intent_id=intent_id,
        message_id=message_id,
        task_id=self.request.id,
    )


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=10)
def relay_notification_outbox_task(self):
    now = timezone.now()
    with transaction.atomic():
        pending_rows = (
            NotificationOutbox.objects.select_for_update(skip_locked=True)
            .filter(status__in=[NotificationOutbox.Status.PENDING, NotificationOutbox.Status.FAILED])
            .filter(models.Q(available_at__isnull=True) | models.Q(available_at__lte=now))
            .order_by("created_at", "id")[:100]
        )
        rows = list(pending_rows)
        if not rows:
            return {"processed": 0}
        NotificationOutbox.objects.filter(id__in=[row.id for row in rows]).update(status=NotificationOutbox.Status.PROCESSING, attempts=models.F("attempts") + 1, updated_at=now)

    processed = 0
    for row in rows:
        try:
            if row.aggregate_type == "notification_campaign" and row.event_type == "notification.campaign.dispatch":
                task = execute_notification_campaign_task.delay(row.payload.get("campaign_id"), row.payload.get("request_id", ""))
                row.payload = {**(row.payload or {}), "downstream_task_id": getattr(task, "id", "")}
            elif row.aggregate_type == "notification_intent" and row.event_type == "notification.sms_otp.dispatch":
                task = execute_sms_otp_intent_task.delay(row.payload.get("intent_id"), row.payload.get("message_id"))
                row.payload = {**(row.payload or {}), "downstream_task_id": getattr(task, "id", "")}
            elif row.aggregate_type == "notification_intent" and row.event_type == "notification.email_otp.dispatch":
                task = execute_email_otp_intent_task.delay(row.payload.get("intent_id"), row.payload.get("message_id"))
                row.payload = {**(row.payload or {}), "downstream_task_id": getattr(task, "id", "")}
            row.status = NotificationOutbox.Status.PROCESSING
            row.last_error = ""
            row.updated_at = timezone.now()
            row.save(update_fields=["status", "last_error", "updated_at", "payload"])
            processed += 1
        except Exception as exc:  # noqa: BLE001
            row.status = NotificationOutbox.Status.FAILED
            row.last_error = str(exc)[:2000]
            row.updated_at = timezone.now()
            row.save(update_fields=["status", "last_error", "updated_at"])
            logger.exception("relay_notification_outbox_task failed outbox_id=%s", row.id)
            raise
    return {"processed": processed}


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def reconcile_notification_outbox_task(self):
    requeued = NotificationCenterService.requeue_stuck_outbox()
    if requeued:
        relay_notification_outbox_task.delay()
    return {"requeued": requeued}


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def poll_sms_delivery_receipts_task(self):
    return NotificationCenterService.poll_pending_sms_deliveries()
