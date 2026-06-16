"""用药计划保存成功后挂载公共 APNs 通知（事务提交后触发）。"""

from __future__ import annotations

from django.db import transaction

from medical.models import MedicationPlan
from medical.services.health_resource_change_notification_service import (
    HealthResourceChangeNotificationService,
)


def schedule_medication_plan_health_notification(
    *,
    actor_user,
    plan: MedicationPlan,
    created: bool,
    request_id: str = "",
) -> None:
    if not plan.reminder_enabled:
        return
    if plan.status != MedicationPlan.Status.ACTIVE:
        return
    if not plan.member_id:
        return

    action = "created" if created else "updated"
    plan_id = plan.id
    member_id = plan.member_id
    user = actor_user

    def _send():
        HealthResourceChangeNotificationService.notify_owner_resource_changed(
            actor_user=user,
            member_id=member_id,
            resource_type="medication_plan",
            resource_id=plan_id,
            action=action,
            request_id=request_id,
        )

    transaction.on_commit(_send)
