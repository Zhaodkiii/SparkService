"""统一权限入口：视图层通过本模块校验成员访问，不直接散落调用 binding_service.ensure_*。"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import QuerySet

from hospital_care.exceptions import HospitalCareError
from medical.permissions import assert_member_access, filter_queryset_by_member_binding
from medical.services import member_binding_service as binding_service
from medical.services import member_permission_service as permission_service
from medical.services.member_binding_service import ensure_can_share_member
from medical.services.member_permission_service import MemberPermissionDenied


class MemberPermissionGate:
    @staticmethod
    def is_development_doctor(user: User) -> bool:
        """开发环境：判断是否为有效医生账号。"""
        try:
            from hospital_care.selectors.doctor_workspace import get_active_doctor

            get_active_doctor(user=user)
            return True
        except HospitalCareError:
            return False

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
        # 开发环境策略：有效医生可直接查看医疗资料，不要求先建立患者绑定
        # 或接管问诊。写入、分享、删除等操作仍由各自的 require_* 权限控制。
        if MemberPermissionGate.is_development_doctor(user):
            return queryset

        # 患者端继续按成员绑定授权。
        member_ids = set(binding_service.accessible_member_ids(user))
        if not member_ids:
            return queryset.none()
        return queryset.filter(**{f"{member_field}__in": member_ids})

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
