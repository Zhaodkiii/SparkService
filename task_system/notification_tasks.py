import logging

from celery import shared_task
from django.utils import timezone

from task_system.models import TaskNotification, TaskNotificationStatus

logger = logging.getLogger("task.notification")


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def dispatch_task_notification_task(self, task_notification_id: int):
    """服务端任务提醒调度（可选）。

    当前默认只做状态落库与日志记录，后续可在这里对接 APNs/SMS。
    """

    notification = TaskNotification.objects.filter(id=task_notification_id).first()
    if notification is None:
        logger.warning("task notification not found id=%s", task_notification_id)
        return {"status": "not_found"}

    logger.info(
        "dispatch task notification id=%s task_id=%s channel=%s",
        notification.id,
        notification.task_id,
        notification.channel,
    )

    notification.status = TaskNotificationStatus.SENT
    notification.sent_at = timezone.now()
    notification.save(update_fields=["status", "sent_at", "updated_at"])
    return {"status": "sent", "task_notification_id": notification.id}
