"""成员分享权限档位与 role 映射（§18）。"""

from __future__ import annotations

from medical.models import UserMemberBinding

PERMISSION_MANAGE = "manage"
PERMISSION_EDIT = "edit"
PERMISSION_VIEW = "view"

VALID_PERMISSIONS = frozenset({PERMISSION_MANAGE, PERMISSION_EDIT, PERMISSION_VIEW})

_DEFAULT_PERMISSION = PERMISSION_EDIT


def role_to_permission(role: str) -> str:
    if role in (UserMemberBinding.Role.OWNER, UserMemberBinding.Role.ADMIN):
        return PERMISSION_MANAGE
    if role == UserMemberBinding.Role.EDITOR:
        return PERMISSION_EDIT
    return PERMISSION_VIEW


def permission_to_role(permission: str) -> str:
    mapping = {
        PERMISSION_MANAGE: UserMemberBinding.Role.ADMIN,
        PERMISSION_EDIT: UserMemberBinding.Role.EDITOR,
        PERMISSION_VIEW: UserMemberBinding.Role.VIEWER,
    }
    if permission not in mapping:
        raise ValueError("invalid_permission")
    return mapping[permission]


def resolve_share_role_from_request(data: dict | None, *, default_permission: str = _DEFAULT_PERMISSION) -> str:
    """从请求体解析分享/邀请授予的 binding role；优先 ``permission``，兼容 ``role``。"""
    payload = data or {}
    permission = (payload.get("permission") or "").strip().lower()
    role = (payload.get("role") or "").strip()

    if permission in VALID_PERMISSIONS:
        return permission_to_role(permission)

    if role in (
        UserMemberBinding.Role.ADMIN,
        UserMemberBinding.Role.EDITOR,
        UserMemberBinding.Role.VIEWER,
    ):
        return role

    if role == UserMemberBinding.Role.OWNER:
        return UserMemberBinding.Role.ADMIN

    default = default_permission if default_permission in VALID_PERMISSIONS else _DEFAULT_PERMISSION
    return permission_to_role(default)
