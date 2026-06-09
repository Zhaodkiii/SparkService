"""饮食营养权限封装。"""

from __future__ import annotations

from django.contrib.auth.models import User

from medical.services.member_permission_gate import MemberPermissionGate
from medical.services.member_permission_service import MemberPermissionDenied


class NutritionPermissionGate:
    @staticmethod
    def require_view(user: User, member_id: int):
        return MemberPermissionGate.require_access(user, member_id)

    @staticmethod
    def require_write(user: User, member_id: int):
        return MemberPermissionGate.require_create(user, member_id)

    @staticmethod
    def require_edit(user: User, member_id: int):
        return MemberPermissionGate.require_edit(user, member_id)

    @staticmethod
    def require_delete(user: User, member_id: int):
        return MemberPermissionGate.require_delete(user, member_id)


__all__ = ["NutritionPermissionGate", "MemberPermissionDenied"]
