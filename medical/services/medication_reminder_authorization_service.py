"""计划级本机提醒授权：服务端统一管理非本人服药计划的本地提醒资格。"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.models import User

from medical.models import MedicationPlan, MedicationReminderLocalAuthorization
from medical.services.member_binding_service import get_active_binding


@dataclass(frozen=True)
class MedicationReminderAuthorizationContext:
    plan: MedicationPlan
    binding_relationship: str
    is_self_member: bool
    authorization: MedicationReminderLocalAuthorization | None


def load_authorization_context(*, user: User, plan_id: int) -> MedicationReminderAuthorizationContext:
    plan = (
        MedicationPlan.objects.select_related("member")
        .filter(id=plan_id, is_deleted=False, member__is_deleted=False)
        .first()
    )
    if plan is None:
        raise MedicationPlan.DoesNotExist

    binding = get_active_binding(user=user, member_id=plan.member_id)
    if binding is None:
        raise PermissionError("permission_denied")

    authorization = (
        MedicationReminderLocalAuthorization.objects.filter(
            user=user,
            medication_plan_id=plan.id,
        )
        .select_related("member", "medication_plan")
        .first()
    )
    return MedicationReminderAuthorizationContext(
        plan=plan,
        binding_relationship=binding.relationship,
        is_self_member=binding.relationship == "self",
        authorization=authorization,
    )


def serialize_authorization_context(
    *,
    user: User,
    context: MedicationReminderAuthorizationContext,
) -> dict:
    authorization = context.authorization
    if context.is_self_member:
        enabled = True
        exists = authorization is not None
        source = authorization.source if authorization else "self_member"
        updated_at = authorization.updated_at.isoformat() if authorization else None
        identifier = authorization.id if authorization else None
    else:
        enabled = bool(authorization and authorization.enabled)
        exists = authorization is not None
        source = authorization.source if authorization else ""
        updated_at = authorization.updated_at.isoformat() if authorization else None
        identifier = authorization.id if authorization else None

    return {
        "id": identifier,
        "user_id": user.id,
        "member_id": context.plan.member_id,
        "medication_plan_id": context.plan.id,
        "enabled": enabled,
        "exists": exists,
        "is_self_member": context.is_self_member,
        "source": source,
        "updated_at": updated_at,
    }


def upsert_local_authorization(
    *,
    user: User,
    plan_id: int,
    enabled: bool,
    source: str,
) -> dict:
    context = load_authorization_context(user=user, plan_id=plan_id)
    plan = context.plan
    if not plan.reminder_enabled or plan.status != MedicationPlan.Status.ACTIVE:
        raise ValueError("invalid_plan_reminder_state")

    if context.is_self_member:
        return serialize_authorization_context(user=user, context=context)

    authorization, created = MedicationReminderLocalAuthorization.objects.get_or_create(
        user=user,
        medication_plan=plan,
        defaults={
            "member": plan.member,
            "enabled": enabled,
            "source": source,
        },
    )
    if not created:
        authorization.member = plan.member
        authorization.enabled = enabled
        authorization.source = source
        authorization.save(update_fields=["member", "enabled", "source", "updated_at"])

    refreshed = MedicationReminderAuthorizationContext(
        plan=plan,
        binding_relationship=context.binding_relationship,
        is_self_member=False,
        authorization=authorization,
    )
    return serialize_authorization_context(user=user, context=refreshed)


def disable_local_authorization(*, user: User, plan_id: int) -> dict:
    context = load_authorization_context(user=user, plan_id=plan_id)
    authorization = context.authorization
    if authorization is not None and authorization.enabled:
        authorization.enabled = False
        authorization.save(update_fields=["enabled", "updated_at"])
        context = MedicationReminderAuthorizationContext(
            plan=context.plan,
            binding_relationship=context.binding_relationship,
            is_self_member=context.is_self_member,
            authorization=authorization,
        )
    return serialize_authorization_context(user=user, context=context)
