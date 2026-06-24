"""按需用药（as_needed）服药计划创建辅助逻辑。"""

from __future__ import annotations

from medical.models import MedicationPlan


def find_reusable_as_needed_plan(
    *,
    member_id: int,
    medicine_box_id: int | None,
) -> MedicationPlan | None:
    """按需用药创建前，查找可复用的已有计划。

    仅在创建请求 ``status=as_needed`` 且携带 ``medicine_box`` 时调用。
    若同一成员下已存在关联该药箱的服药计划，则返回最新一条，避免重复建档。
    """
    if member_id is None or medicine_box_id is None:
        return None

    return (
        MedicationPlan.objects.filter(
            is_deleted=False,
            member_id=member_id,
            medicine_box_id=medicine_box_id,
        )
        .order_by("-updated_at", "-id")
        .first()
    )
