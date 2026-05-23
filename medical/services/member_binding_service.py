"""用户-成员绑定：权限判断、创建、解绑与能力位计算。"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Iterable

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q

from medical.models import (
    ExaminationReport,
    HealthExamReport,
    MedicalCase,
    MedicationPlan,
    Member,
    UserMemberBinding,
)
from medical.services.member_permission_levels import (
    role_to_permission,
    permission_to_role,
)


@dataclass(frozen=True)
class MemberCapabilities:
    binding_id: int
    binding_role: str
    permission: str
    relationship: str
    shared_user_count: int
    can_view: bool
    can_create: bool
    can_edit: bool
    can_delete: bool
    can_delete_medical: bool
    can_share: bool
    can_unbind: bool
    can_manage_bindings: bool
    can_remove_shared_binding: bool


def active_bindings_qs():
    return UserMemberBinding.objects.filter(status=UserMemberBinding.Status.ACTIVE)


def get_active_binding(*, user: User, member_id: int) -> UserMemberBinding | None:
    return (
        active_bindings_qs()
        .select_related("member")
        .filter(user=user, member_id=member_id, member__is_deleted=False)
        .first()
    )


def accessible_member_ids(user: User) -> list[int]:
    return list(
        active_bindings_qs()
        .filter(user=user, member__is_deleted=False)
        .values_list("member_id", flat=True)
    )


def accessible_members_queryset(user: User):
    return Member.objects.filter(
        id__in=accessible_member_ids(user),
        is_deleted=False,
    )


def count_active_bindings(member_id: int) -> int:
    return active_bindings_qs().filter(member_id=member_id).count()


def compute_capabilities(binding: UserMemberBinding) -> MemberCapabilities:
    role = binding.role
    permission = role_to_permission(role)
    shared_count = count_active_bindings(binding.member_id)
    only_binding = shared_count <= 1

    is_owner = role == UserMemberBinding.Role.OWNER
    is_manage = role in (UserMemberBinding.Role.OWNER, UserMemberBinding.Role.ADMIN)
    can_write_medical = role in (
        UserMemberBinding.Role.OWNER,
        UserMemberBinding.Role.ADMIN,
        UserMemberBinding.Role.EDITOR,
    )

    can_view = True
    can_create = can_write_medical
    can_edit = can_write_medical
    can_delete_medical = is_manage
    can_delete = is_manage and only_binding
    can_share = is_manage
    can_unbind = True
    can_manage_bindings = is_owner
    can_remove_shared_binding = is_manage

    return MemberCapabilities(
        binding_id=binding.id,
        binding_role=role,
        permission=permission,
        relationship=binding.relationship,
        shared_user_count=shared_count,
        can_view=can_view,
        can_create=can_create,
        can_edit=can_edit,
        can_delete=can_delete,
        can_delete_medical=can_delete_medical,
        can_share=can_share,
        can_unbind=can_unbind,
        can_manage_bindings=can_manage_bindings,
        can_remove_shared_binding=can_remove_shared_binding,
    )


def capabilities_to_dict(caps: MemberCapabilities) -> dict:
    return {
        "can_view": caps.can_view,
        "can_create": caps.can_create,
        "can_edit": caps.can_edit,
        "can_delete": caps.can_delete,
        "can_delete_medical": caps.can_delete_medical,
        "can_share": caps.can_share,
        "can_unbind": caps.can_unbind,
        "can_manage_bindings": caps.can_manage_bindings,
        "can_remove_shared_binding": caps.can_remove_shared_binding,
    }


@transaction.atomic
def create_owner_binding(
    *,
    user: User,
    member: Member,
    relationship: str,
    invited_by: User | None = None,
) -> UserMemberBinding:
    binding, created = UserMemberBinding.objects.get_or_create(
        user=user,
        member=member,
        defaults={
            "relationship": relationship or "self",
            "role": UserMemberBinding.Role.OWNER,
            "status": UserMemberBinding.Status.ACTIVE,
            "invited_by": invited_by,
        },
    )
    if not created:
        binding.relationship = relationship or binding.relationship
        binding.role = UserMemberBinding.Role.OWNER
        binding.status = UserMemberBinding.Status.ACTIVE
        binding.save(update_fields=["relationship", "role", "status", "updated_at"])
    return binding


@transaction.atomic
def accept_share_binding(
    *,
    user: User,
    member: Member,
    relationship: str,
    custom_relationship: str,
    role: str,
    invited_by: User,
) -> tuple[UserMemberBinding, bool]:
    resolved_relationship = relationship
    if relationship == "other" and custom_relationship.strip():
        resolved_relationship = custom_relationship.strip()[:20]

    binding, created = UserMemberBinding.objects.get_or_create(
        user=user,
        member=member,
        defaults={
            "relationship": resolved_relationship,
            "role": role or UserMemberBinding.Role.VIEWER,
            "status": UserMemberBinding.Status.ACTIVE,
            "invited_by": invited_by,
        },
    )
    if not created:
        binding.relationship = resolved_relationship
        if binding.status != UserMemberBinding.Status.ACTIVE:
            binding.status = UserMemberBinding.Status.ACTIVE
        binding.invited_by = invited_by
        binding.save(update_fields=["relationship", "status", "invited_by", "updated_at"])
    return binding, created


def revoke_binding(binding: UserMemberBinding) -> None:
    binding.status = UserMemberBinding.Status.REVOKED
    binding.save(update_fields=["status", "updated_at"])


def ensure_can_manage_bindings(*, user: User, member_id: int) -> UserMemberBinding:
    binding = ensure_can_access_member(user=user, member_id=member_id)
    caps = compute_capabilities(binding)
    if not caps.can_manage_bindings:
        raise PermissionError("permission_denied")
    return binding


@transaction.atomic
def change_binding_role(binding: UserMemberBinding, new_role: str) -> UserMemberBinding:
    if new_role not in (
        UserMemberBinding.Role.ADMIN,
        UserMemberBinding.Role.EDITOR,
        UserMemberBinding.Role.VIEWER,
    ):
        raise ValueError("invalid_role")
    if binding.role == UserMemberBinding.Role.OWNER:
        raise ValueError("cannot_change_owner_role")
    binding.role = new_role
    binding.save(update_fields=["role", "updated_at"])
    return binding


@transaction.atomic
def change_binding_permission(binding: UserMemberBinding, permission: str) -> UserMemberBinding:
    new_role = permission_to_role(permission)
    return change_binding_role(binding, new_role)


@transaction.atomic
def remove_binding(binding: UserMemberBinding) -> None:
    if binding.role == UserMemberBinding.Role.OWNER:
        raise ValueError("cannot_remove_owner")
    revoke_binding(binding)


@transaction.atomic
def transfer_owner(*, current_owner_binding: UserMemberBinding, target_binding: UserMemberBinding) -> None:
    if current_owner_binding.member_id != target_binding.member_id:
        raise ValueError("member_mismatch")
    if current_owner_binding.role != UserMemberBinding.Role.OWNER:
        raise ValueError("not_owner")
    if target_binding.status != UserMemberBinding.Status.ACTIVE:
        raise ValueError("target_inactive")
    if target_binding.role == UserMemberBinding.Role.OWNER:
        return

    current_owner_binding.role = UserMemberBinding.Role.ADMIN
    current_owner_binding.save(update_fields=["role", "updated_at"])
    target_binding.role = UserMemberBinding.Role.OWNER
    target_binding.save(update_fields=["role", "updated_at"])


@transaction.atomic
def delete_member_profile(member: Member) -> None:
    member.soft_delete()
    active_bindings_qs().filter(member=member).update(status=UserMemberBinding.Status.REVOKED)


def member_medical_overview(member_id: int) -> dict:
    return {
        "medical_case_count": MedicalCase.objects.filter(member_id=member_id, is_deleted=False).count(),
        "health_exam_report_count": HealthExamReport.objects.filter(member_id=member_id, is_deleted=False).count(),
        "examination_report_count": ExaminationReport.objects.filter(member_id=member_id, is_deleted=False).count(),
        "medication_plan_count": MedicationPlan.objects.filter(member_id=member_id, is_deleted=False).count(),
        "last_updated_at": _latest_member_activity_at(member_id),
    }


def _latest_member_activity_at(member_id: int):
    candidates = []
    for model in (MedicalCase, HealthExamReport, ExaminationReport, MedicationPlan):
        latest = (
            model.objects.filter(member_id=member_id, is_deleted=False)
            .order_by("-updated_at")
            .values_list("updated_at", flat=True)
            .first()
        )
        if latest:
            candidates.append(latest)
    return max(candidates) if candidates else None


def shared_users_payload(*, member_id: int, viewer: User, include_details: bool) -> list[dict]:
    if not include_details:
        return []
    bindings = (
        active_bindings_qs()
        .select_related("user")
        .filter(member_id=member_id)
        .order_by("created_at", "id")
    )
    rows = []
    for item in bindings:
        display = _masked_user_label(item.user)
        caps = compute_capabilities(item)
        rows.append(
            {
                "binding_id": item.id,
                "user_id": item.user_id,
                "display_name": display,
                "relationship": item.relationship,
                "role": item.role,
                "permission": caps.permission,
                "capabilities": capabilities_to_dict(caps),
                "is_self": item.user_id == viewer.id,
                "bound_at": item.created_at,
            }
        )
    return rows


def _masked_user_label(user: User) -> str:
    email = (user.email or "").strip()
    if email and "@" in email:
        local, domain = email.split("@", 1)
        masked_local = local[:1] + "***" if local else "***"
        return f"{masked_local}@{domain}"
    username = (user.username or "").strip()
    if username:
        return username[:1] + "***"
    return f"用户{user.id}"


def ensure_can_access_member(*, user: User, member_id: int) -> UserMemberBinding:
    binding = get_active_binding(user=user, member_id=member_id)
    if binding is None:
        raise PermissionError("permission_denied")
    return binding


def ensure_can_create_member_resource(*, user: User, member_id: int) -> UserMemberBinding:
    binding = ensure_can_access_member(user=user, member_id=member_id)
    caps = compute_capabilities(binding)
    if not caps.can_create:
        raise PermissionError("permission_denied")
    return binding


def ensure_can_edit_member_resource(*, user: User, member_id: int) -> UserMemberBinding:
    binding = ensure_can_access_member(user=user, member_id=member_id)
    caps = compute_capabilities(binding)
    if not caps.can_edit:
        raise PermissionError("permission_denied")
    return binding


def ensure_can_delete_member_resource(*, user: User, member_id: int) -> UserMemberBinding:
    binding = ensure_can_access_member(user=user, member_id=member_id)
    caps = compute_capabilities(binding)
    if not caps.can_delete_medical:
        raise PermissionError("permission_denied")
    return binding


def ensure_can_remove_shared_binding(*, user: User, member_id: int) -> UserMemberBinding:
    binding = ensure_can_access_member(user=user, member_id=member_id)
    caps = compute_capabilities(binding)
    if not caps.can_remove_shared_binding:
        raise PermissionError("permission_denied")
    return binding


# Backward-compatible aliases
ensure_can_write_medical_member = ensure_can_create_member_resource
ensure_can_edit_member = ensure_can_edit_member_resource


def ensure_can_share_member(*, user: User, member_id: int) -> UserMemberBinding:
    binding = ensure_can_access_member(user=user, member_id=member_id)
    caps = compute_capabilities(binding)
    if not caps.can_share:
        raise PermissionError("permission_denied")
    return binding


def new_share_nonce() -> str:
    return secrets.token_urlsafe(12)
