"""家庭药箱汇总：按入口成员推导创建者名下药品集合。"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Q, QuerySet

from medical.models import MedicineBox, Member
from medical.services.member_permission_gate import MemberPermissionGate


def family_medicine_cabinet_queryset(*, user: User, entry_member_id: int) -> QuerySet[MedicineBox]:
    """返回入口成员所属创建者名下的家庭药箱药品（成员绑定 + 公共药品）。"""
    binding = MemberPermissionGate.require_access(user=user, member_id=entry_member_id)
    owner_user_id = binding.member.user_id
    member_ids = list(
        Member.objects.filter(user_id=owner_user_id, is_deleted=False).values_list("id", flat=True)
    )
    return (
        MedicineBox.objects.filter(is_deleted=False)
        .filter(Q(member_id__in=member_ids) | Q(member_id__isnull=True, user_id=owner_user_id))
        .select_related("member")
        .order_by("-updated_at", "-id")
    )
