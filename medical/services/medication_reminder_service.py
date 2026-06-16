"""用药提醒聚合查询：为客户端本地通知补全提供开启提醒计划与窗口记录。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import User
from django.utils import timezone

from accounts.services.device_session_service import DeviceSessionService
from medical.models import MedicationPlan, MedicationRecord, Member
from medical.serializers import MedicationPlanSerializer, MedicationRecordSerializer
from medical.services.member_binding_service import (
    _masked_user_label,
    active_bindings_qs,
    compute_capabilities,
    get_active_binding,
)
from medical.services.medication_record_query import (
    MedicationRecordScheduledRange,
    apply_medication_record_scheduled_range,
)

MAX_WINDOW_DAYS = 14


@dataclass(frozen=True)
class MedicationReminderWindow:
    start_date: date
    end_date: date


def resolve_window_dates(
    *,
    window_start_date: date | None,
    window_end_date: date | None,
) -> MedicationReminderWindow:
    today = timezone.localdate()
    start = window_start_date or today
    end = window_end_date or (start + timedelta(days=7))
    if end < start:
        end = start
    max_end = start + timedelta(days=MAX_WINDOW_DAYS)
    if end > max_end:
        end = max_end
    return MedicationReminderWindow(start_date=start, end_date=end)


def user_apns_capability(user: User) -> dict:
    device = DeviceSessionService.apns_trusted_device_for_user(user=user)
    return {
        "has_apns": device is not None,
        "notifications_enabled": bool(device and device.notifications_enabled),
    }


def list_self_owners(*, member_id: int, exclude_user_id: int) -> list[dict]:
    bindings = (
        active_bindings_qs()
        .select_related("user")
        .filter(
            member_id=member_id,
            relationship="self",
        )
        .exclude(user_id=exclude_user_id)
        .order_by("created_at", "id")
    )
    rows = []
    seen: set[int] = set()
    for binding in bindings:
        if binding.user_id in seen:
            continue
        seen.add(binding.user_id)
        apns = user_apns_capability(binding.user)
        rows.append(
            {
                "user_id": binding.user_id,
                "display_name": _masked_user_label(binding.user),
                **apns,
            }
        )
    return rows


def build_member_notification_ownership(*, user: User, member_id: int) -> dict | None:
    binding = get_active_binding(user=user, member_id=member_id)
    if binding is None:
        return None
    member = binding.member
    caps = compute_capabilities(binding)
    self_owners = list_self_owners(member_id=member_id, exclude_user_id=user.id)
    is_self_member = binding.relationship == "self"
    return {
        "member_id": member.id,
        "member_name": member.name,
        "current_user_relationship": binding.relationship,
        "is_current_user_self_member": is_self_member,
        "can_share": caps.can_share,
        "can_write": caps.can_edit,
        "has_other_self_owner": len(self_owners) > 0,
        "self_owners": self_owners,
    }


def _window_datetime_bounds(window: MedicationReminderWindow) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(window.start_date, time.min), tz)
    end_exclusive = timezone.make_aware(
        datetime.combine(window.end_date + timedelta(days=1), time.min),
        tz,
    )
    return start_dt, end_exclusive


def query_enabled_plans_for_member(*, member_id: int, window: MedicationReminderWindow):
    return (
        MedicationPlan.objects.filter(
            is_deleted=False,
            member_id=member_id,
            reminder_enabled=True,
            status=MedicationPlan.Status.ACTIVE,
            start_date__lte=window.end_date,
        )
        .filter(
            models_q_end_date_covers_window(window.start_date)
        )
        .select_related("member", "medical_case", "medicine_box", "prescription")
        .order_by("start_date", "id")
    )


def models_q_end_date_covers_window(window_start: date):
    from django.db.models import Q

    return Q(end_date__isnull=True) | Q(end_date__gte=window_start)


def build_enabled_plans_response(
    *,
    user: User,
    window: MedicationReminderWindow,
    include_records: bool,
    request,
) -> dict:
    member_ids = list(
        active_bindings_qs()
        .filter(user=user, member__is_deleted=False)
        .values_list("member_id", flat=True)
        .distinct()
    )
    members = {
        item.id: item
        for item in Member.objects.filter(id__in=member_ids, is_deleted=False)
    }
    bindings = {
        item.member_id: item
        for item in active_bindings_qs()
        .select_related("member")
        .filter(user=user, member_id__in=member_ids)
    }

    record_start, record_end_exclusive = _window_datetime_bounds(window)
    scheduled_range = MedicationRecordScheduledRange(
        start=record_start,
        end_exclusive=record_end_exclusive,
    )

    groups = []
    for member_id in sorted(member_ids):
        member = members.get(member_id)
        binding = bindings.get(member_id)
        if member is None or binding is None:
            continue
        caps = compute_capabilities(binding)
        plans_qs = query_enabled_plans_for_member(member_id=member_id, window=window)
        plan_serializer = MedicationPlanSerializer(plans_qs, many=True, context={"request": request})
        records_data = []
        if include_records:
            records_qs = MedicationRecord.objects.filter(member_id=member_id).select_related(
                "plan",
                "plan__medicine_box",
            )
            records_qs = apply_medication_record_scheduled_range(records_qs, scheduled_range)
            record_serializer = MedicationRecordSerializer(records_qs, many=True, context={"request": request})
            records_data = record_serializer.data

        groups.append(
            {
                "member": {
                    "id": member.id,
                    "name": member.name,
                    "relationship": binding.relationship,
                    "is_self_member": binding.relationship == "self",
                    "binding_role": binding.role,
                    "can_share": caps.can_share,
                    "can_write": caps.can_edit,
                },
                "self_owners": list_self_owners(member_id=member_id, exclude_user_id=user.id),
                "plans": plan_serializer.data,
                "records": records_data,
            }
        )

    return {
        "window_start_date": window.start_date.isoformat(),
        "window_end_date": window.end_date.isoformat(),
        "members": groups,
    }
