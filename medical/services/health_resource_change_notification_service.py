"""公共健康资源变更 APNs：告知其他本人绑定用户资料被维护，不用于剂次定时提醒。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.contrib.auth.models import User

from notification_center.models import NotificationMessage
from notification_center.services import NotificationCenterService
from medical.services.member_binding_service import (
    _masked_user_label,
    active_bindings_qs,
)
from medical.services.medication_reminder_service import user_apns_capability

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HealthResourceNotificationPolicy:
    notify_self_owners: bool = True
    notify_managers_when_no_self_owner: bool = False
    notify_managers_when_self_owner_exists: bool = False
    manager_roles: tuple[str, ...] = ("owner", "admin")


POLICY_BY_RESOURCE = {
    "medication_plan": HealthResourceNotificationPolicy(
        notify_self_owners=True,
        notify_managers_when_no_self_owner=False,
        notify_managers_when_self_owner_exists=False,
    ),
}


class HealthResourceChangeNotificationService:
    @staticmethod
    def notify_owner_resource_changed(
        *,
        actor_user: User,
        member_id: int,
        resource_type: str,
        resource_id: int,
        action: str,
        request_id: str = "",
    ) -> dict:
        policy = POLICY_BY_RESOURCE.get(resource_type)
        if policy is None:
            return {
                "target_count": 0,
                "sent_count": 0,
                "skipped_count": 0,
                "skipped_reasons": ["policy_disabled"],
            }

        targets = HealthResourceChangeNotificationService._resolve_targets(
            actor_user=actor_user,
            member_id=member_id,
            policy=policy,
        )
        actor_display = _masked_user_label(actor_user)
        title, body = HealthResourceChangeNotificationService._copy_for_resource(
            resource_type=resource_type,
            actor_display_name=actor_display,
        )
        payload = {
            "type": "health_resource_changed",
            "resource_type": resource_type,
            "resource_id": str(resource_id),
            "member_id": str(member_id),
            "action": action,
            "actor_user_id": str(actor_user.id),
        }

        sent_count = 0
        skipped_count = 0
        skipped_reasons: list[str] = []
        target_rows = []

        for target_user, reason in targets:
            apns = user_apns_capability(target_user)
            if not apns["has_apns"] or not apns["notifications_enabled"]:
                skipped_count += 1
                skipped_reasons.append("no_apns_device")
                target_rows.append(
                    {
                        "user_id": target_user.id,
                        "target_reason": reason,
                        "channel": "apns",
                        "status": "skipped",
                    }
                )
                continue
            try:
                msgs = NotificationCenterService.send_to_user_sync(
                    campaign_id=None,
                    user_id=target_user.id,
                    channels=[NotificationMessage.Channel.APNS],
                    title=title,
                    body=body,
                    payload=payload,
                    created_by_id=actor_user.id,
                    request_id=request_id,
                    business_scene="medical.resource.updated",
                    business_reference_type=resource_type,
                    business_id=str(resource_id),
                    idempotency_key=f"medical.resource.updated:{resource_type}:{resource_id}:{target_user.id}:{action}:{request_id or 'event'}",
                    source="medical.health_resource_change",
                    actor_type="user",
                    actor_id=str(actor_user.id),
                )
                msg = msgs[0] if msgs else None
                ok = msg and msg.status in (
                    NotificationMessage.Status.ACCEPTED,
                    NotificationMessage.Status.DELIVERED,
                    NotificationMessage.Status.SENT,
                    NotificationMessage.Status.PARTIAL,
                )
                if ok:
                    sent_count += 1
                    target_rows.append(
                        {
                            "user_id": target_user.id,
                            "target_reason": reason,
                            "channel": "apns",
                            "status": "sent",
                        }
                    )
                else:
                    skipped_count += 1
                    skipped_reasons.append("send_failed")
                    target_rows.append(
                        {
                            "user_id": target_user.id,
                            "target_reason": reason,
                            "channel": "apns",
                            "status": "failed",
                        }
                    )
            except Exception as exc:
                logger.warning(
                    "health_resource_changed notify failed user_id=%s error=%s",
                    target_user.id,
                    exc,
                )
                skipped_count += 1
                skipped_reasons.append("send_failed")

        return {
            "target_count": len(targets),
            "sent_count": sent_count,
            "skipped_count": skipped_count,
            "targets": target_rows,
            "skipped_reasons": skipped_reasons,
        }

    @staticmethod
    def _resolve_targets(
        *,
        actor_user: User,
        member_id: int,
        policy: HealthResourceNotificationPolicy,
    ) -> list[tuple[User, str]]:
        bindings = (
            active_bindings_qs()
            .select_related("user")
            .filter(member_id=member_id)
            .order_by("created_at", "id")
        )
        targets: list[tuple[User, str]] = []
        seen: set[int] = set()

        if policy.notify_self_owners:
            for binding in bindings:
                if binding.relationship != "self":
                    continue
                if binding.user_id == actor_user.id:
                    continue
                if binding.user_id in seen:
                    continue
                seen.add(binding.user_id)
                targets.append((binding.user, "self_owner"))

        has_self_targets = len(targets) > 0

        if not has_self_targets and policy.notify_managers_when_no_self_owner:
            for binding in bindings:
                if binding.role not in policy.manager_roles:
                    continue
                if binding.user_id == actor_user.id:
                    continue
                if binding.user_id in seen:
                    continue
                seen.add(binding.user_id)
                reason = "manager_owner" if binding.role == "owner" else "manager_admin"
                targets.append((binding.user, reason))

        if has_self_targets and policy.notify_managers_when_self_owner_exists:
            for binding in bindings:
                if binding.role not in policy.manager_roles:
                    continue
                if binding.user_id == actor_user.id:
                    continue
                if binding.user_id in seen:
                    continue
                seen.add(binding.user_id)
                reason = "manager_owner" if binding.role == "owner" else "manager_admin"
                targets.append((binding.user, reason))

        return targets

    @staticmethod
    def _copy_for_resource(*, resource_type: str, actor_display_name: str) -> tuple[str, str]:
        if resource_type == "medication_plan":
            title = "用药计划已更新"
            if actor_display_name:
                body = f"{actor_display_name} 维护了你的用药计划，打开应用查看详情"
            else:
                body = "有人维护了你的用药计划，打开应用查看详情"
            return title, body
        return "健康资料已更新", "有人维护了你的健康资料，打开应用查看详情"
