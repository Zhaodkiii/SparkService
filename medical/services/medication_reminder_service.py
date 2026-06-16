"""用药提醒聚合查询：为客户端本地通知补全提供开启提醒计划与窗口记录。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from accounts.services.device_session_service import DeviceSessionService
from medical.models import MedicationPlan, MedicationRecord, MedicationReminderLocalAuthorization
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
        .filter(member_id=member_id, relationship="self")
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
    caps = compute_capabilities(binding)
    self_owners = list_self_owners(member_id=member_id, exclude_user_id=user.id)
    return {
        "member_id": binding.member.id,
        "member_name": binding.member.name,
        "current_user_relationship": binding.relationship,
        "is_current_user_self_member": binding.relationship == "self",
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


def models_q_end_date_covers_window(window_start: date):
    return Q(end_date__isnull=True) | Q(end_date__gte=window_start)


def build_enabled_plans_response(
    *,
    user: User,
    window: MedicationReminderWindow,
    include_records: bool,
    request,
) -> dict:
    bindings = list(
        active_bindings_qs()
        .select_related("member")
        .filter(user=user, member__is_deleted=False)
        .order_by("member_id", "created_at", "id")
    )
    binding_by_member_id = {item.member_id: item for item in bindings}
    accessible_member_ids = list(binding_by_member_id.keys())
    self_member_ids = [item.member_id for item in bindings if item.relationship == "self"]

    record_start, record_end_exclusive = _window_datetime_bounds(window)
    scheduled_range = MedicationRecordScheduledRange(
        start=record_start,
        end_exclusive=record_end_exclusive,
    )

    plans_by_member_id: dict[int, list[MedicationPlan]] = {}
    included_plan_ids: set[int] = set()

    if self_member_ids:
        self_plans = (
            MedicationPlan.objects.filter(
                is_deleted=False,
                member_id__in=self_member_ids,
                reminder_enabled=True,
                status=MedicationPlan.Status.ACTIVE,
                start_date__lte=window.end_date,
            )
            .filter(models_q_end_date_covers_window(window.start_date))
            .select_related("member", "medical_case", "medicine_box", "prescription")
            .order_by("member_id", "start_date", "id")
        )
        for plan in self_plans:
            plans_by_member_id.setdefault(plan.member_id, []).append(plan)
            included_plan_ids.add(plan.id)

    if accessible_member_ids:
        authorized_rows = (
            MedicationReminderLocalAuthorization.objects.filter(
                user=user,
                enabled=True,
                member_id__in=accessible_member_ids,
                medication_plan__is_deleted=False,
                medication_plan__member__is_deleted=False,
                medication_plan__reminder_enabled=True,
                medication_plan__status=MedicationPlan.Status.ACTIVE,
                medication_plan__start_date__lte=window.end_date,
                medication_plan__member_id__in=accessible_member_ids,
            )
            .filter(
                Q(medication_plan__end_date__isnull=True)
                | Q(medication_plan__end_date__gte=window.start_date)
            )
            .select_related(
                "member",
                "medication_plan",
                "medication_plan__member",
                "medication_plan__medical_case",
                "medication_plan__medicine_box",
                "medication_plan__prescription",
            )
            .order_by("member_id", "medication_plan__start_date", "medication_plan_id")
        )
        for row in authorized_rows:
            plan = row.medication_plan
            binding = binding_by_member_id.get(plan.member_id)
            if binding is None or binding.relationship == "self":
                continue
            if plan.id in included_plan_ids:
                continue
            plans_by_member_id.setdefault(plan.member_id, []).append(plan)
            included_plan_ids.add(plan.id)

    records_by_member_id: dict[int, list[dict]] = {}
    if include_records and included_plan_ids:
        records_qs = MedicationRecord.objects.filter(
            plan_id__in=included_plan_ids,
            member_id__in=list(plans_by_member_id.keys()),
        ).select_related("plan", "plan__medicine_box")
        records_qs = apply_medication_record_scheduled_range(records_qs, scheduled_range)
        record_rows = MedicationRecordSerializer(records_qs, many=True, context={"request": request}).data
        for row in record_rows:
            member_id = row.get("member")
            if member_id is None:
                continue
            records_by_member_id.setdefault(member_id, []).append(row)

    groups = []
    for member_id in sorted(plans_by_member_id.keys()):
        binding = binding_by_member_id.get(member_id)
        if binding is None:
            continue
        caps = compute_capabilities(binding)
        plan_serializer = MedicationPlanSerializer(
            plans_by_member_id.get(member_id) or [],
            many=True,
            context={"request": request},
        )
        groups.append(
            {
                "member": {
                    "id": binding.member.id,
                    "name": binding.member.name,
                    "relationship": binding.relationship,
                    "is_self_member": binding.relationship == "self",
                    "binding_role": binding.role,
                    "can_share": caps.can_share,
                    "can_write": caps.can_edit,
                },
                "source": "self_member" if binding.relationship == "self" else "authorized_plan",
                "self_owners": list_self_owners(member_id=member_id, exclude_user_id=user.id),
                "plans": plan_serializer.data,
                "records": records_by_member_id.get(member_id, []),
            }
        )

    return {
        "window_start_date": window.start_date.isoformat(),
        "window_end_date": window.end_date.isoformat(),
        "members": groups,
    }
