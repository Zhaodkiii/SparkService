"""成员绑定维度的访问控制辅助。"""

from __future__ import annotations

from django.contrib.auth.models import User

from medical.services import member_binding_service as binding_service


def filter_queryset_by_member_binding(queryset, user: User, *, member_field: str = "member_id"):
    member_ids = binding_service.accessible_member_ids(user)
    if not member_ids:
        return queryset.none()
    return queryset.filter(**{f"{member_field}__in": member_ids})


def assert_member_access(user: User, member_id: int):
    return binding_service.ensure_can_access_member(user=user, member_id=member_id)
