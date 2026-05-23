"""统一成员权限服务（§18.4）：所有接口经此校验，不散落判断。"""

from __future__ import annotations

from django.contrib.auth.models import User

from medical.models import UserMemberBinding
from medical.services import member_binding_service as binding_service
from medical.services.member_permission_levels import role_to_permission


class MemberPermissionDenied(PermissionError):
    def __init__(self, *, required_permission: str, current_permission: str):
        self.required_permission = required_permission
        self.current_permission = current_permission
        super().__init__("permission_denied")


def _deny(*, required: str, binding: UserMemberBinding) -> None:
    raise MemberPermissionDenied(
        required_permission=required,
        current_permission=role_to_permission(binding.role),
    )


def ensure_can_view_member(*, user: User, member_id: int) -> UserMemberBinding:
    return binding_service.ensure_can_access_member(user=user, member_id=member_id)


def ensure_can_create_member_resource(*, user: User, member_id: int) -> UserMemberBinding:
    binding = binding_service.ensure_can_access_member(user=user, member_id=member_id)
    caps = binding_service.compute_capabilities(binding)
    if not caps.can_create:
        _deny(required="edit", binding=binding)
    return binding


def ensure_can_edit_member_resource(*, user: User, member_id: int) -> UserMemberBinding:
    binding = binding_service.ensure_can_access_member(user=user, member_id=member_id)
    caps = binding_service.compute_capabilities(binding)
    if not caps.can_edit:
        _deny(required="edit", binding=binding)
    return binding


def ensure_can_delete_member_resource(*, user: User, member_id: int) -> UserMemberBinding:
    binding = binding_service.ensure_can_access_member(user=user, member_id=member_id)
    caps = binding_service.compute_capabilities(binding)
    if not caps.can_delete_medical:
        _deny(required="manage", binding=binding)
    return binding


def ensure_can_manage_member_bindings(*, user: User, member_id: int) -> UserMemberBinding:
    binding = binding_service.ensure_can_access_member(user=user, member_id=member_id)
    caps = binding_service.compute_capabilities(binding)
    if not caps.can_manage_bindings:
        _deny(required="manage", binding=binding)
    return binding


def ensure_can_remove_shared_binding(*, user: User, member_id: int) -> UserMemberBinding:
    binding = binding_service.ensure_can_access_member(user=user, member_id=member_id)
    caps = binding_service.compute_capabilities(binding)
    if not caps.can_remove_shared_binding:
        _deny(required="manage", binding=binding)
    return binding
