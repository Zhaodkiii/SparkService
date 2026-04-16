"""Celery autodiscover 入口。"""

from task_system.notification_tasks import dispatch_task_notification_task  # noqa: F401
