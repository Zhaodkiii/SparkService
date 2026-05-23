"""统一权限入口：视图层通过本模块校验成员访问，不直接散落调用 binding_service.ensure_*。"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import QuerySet

from medical.permissions import assert_member_access, filter_queryset_by_member_binding
from medical.services import member_permission_service as permission_service
from medical.services.member_binding_service import ensure_can_share_member
from medical.services.member_permission_service import MemberPermissionDenied


class MemberPermissionGate:
    @staticmethod
    def require_access(user: User, member_id: int):
        return permission_service.ensure_can_view_member(user=user, member_id=member_id)

    @staticmethod
    def require_create(user: User, member_id: int):
        return permission_service.ensure_can_create_member_resource(user=user, member_id=member_id)

    @staticmethod
    def require_edit(user: User, member_id: int):
        return permission_service.ensure_can_edit_member_resource(user=user, member_id=member_id)

    @staticmethod
    def require_delete(user: User, member_id: int):
        return permission_service.ensure_can_delete_member_resource(user=user, member_id=member_id)

    @staticmethod
    def require_share(user: User, member_id: int):
        return ensure_can_share_member(user=user, member_id=member_id)

    @staticmethod
    def require_manage(user: User, member_id: int):
        return permission_service.ensure_can_manage_member_bindings(user=user, member_id=member_id)

    @staticmethod
    def require_remove_shared(user: User, member_id: int):
        return permission_service.ensure_can_remove_shared_binding(user=user, member_id=member_id)

    @staticmethod
    def require_write(user: User, member_id: int):
        """兼容旧名：创建/保存医疗资料。"""
        return permission_service.ensure_can_create_member_resource(user=user, member_id=member_id)

    @staticmethod
    def assert_access(user: User, member_id: int):
        return assert_member_access(user, member_id)

    @staticmethod
    def filter_qs(queryset: QuerySet, user: User, *, member_field: str = "member_id") -> QuerySet:
        return filter_queryset_by_member_binding(queryset, user, member_field=member_field)

    @staticmethod
    def permission_denied_response(exc: MemberPermissionDenied, error_response):
        return error_response(
            msg="permission_denied",
            code=-1,
            status_code=403,
            data={
                "required_permission": exc.required_permission,
                "current_permission": exc.current_permission,
            },
        )
