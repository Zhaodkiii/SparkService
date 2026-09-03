from __future__ import annotations

from django.db.models import QuerySet

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import ClinicalConversationBinding, DoctorProfile
from medical.models import Member


def doctor_visible_member_ids(*, doctor: DoctorProfile) -> set[int]:
    """D-007：患者可见范围 = 当前医生 ∩ 当前医院 ∩ 已有授权会话的 member 集合。

    列表、详情、会话列表、会话消息与 AI 总结/风险接口必须使用同一规则。
    """
    rows = (
        ClinicalConversationBinding.objects.filter(
            doctor=doctor,
            hospital_id=doctor.staff_membership.hospital_id,
            thread__is_deleted=False,
            thread__member_id__isnull=False,
        )
        .values_list("thread__member_id", flat=True)
        .distinct()
    )
    return {int(item) for item in rows if item is not None}


def assert_doctor_can_view_member(*, doctor: DoctorProfile, member_id: int) -> None:
    if int(member_id) not in doctor_visible_member_ids(doctor=doctor):
        raise HospitalCareError("PATIENT_NOT_ASSIGNED")


def get_visible_member(*, doctor: DoctorProfile, member_id: int) -> Member:
    """详情/工作台/会话接口统一入口：先校验可见范围，再返回未删除的 Member。"""
    assert_doctor_can_view_member(doctor=doctor, member_id=member_id)
    member = Member.all_objects.filter(pk=int(member_id), is_deleted=False).first()
    if member is None:
        raise HospitalCareError("PATIENT_NOT_ASSIGNED")
    return member


def doctor_patient_conversations(*, doctor: DoctorProfile, member_id: int) -> QuerySet[ClinicalConversationBinding]:
    """D-012：当前医生对该患者有权查看的全部院内会话。

    按最近更新时间倒序；时间相同使用稳定 thread_id 作为最终排序键。
    """
    assert_doctor_can_view_member(doctor=doctor, member_id=member_id)
    return (
        ClinicalConversationBinding.objects.select_related("thread", "hospital", "department", "doctor", "agent")
        .filter(
            doctor=doctor,
            hospital_id=doctor.staff_membership.hospital_id,
            thread__is_deleted=False,
            thread__member_id=int(member_id),
        )
        .order_by("-updated_at", "-thread_id")
    )


def doctor_patient_rows(*, doctor: DoctorProfile) -> list[dict]:
    """D-007~D-010：按患者聚合当前医生的授权会话，产出列表行原始数据。

    返回每行：member_id / service_status / priority_patient / latest_conversation_at / conversation_count。
    排序与筛选手段在 service 层完成；本函数只负责授权集合内的聚合。
    """
    bindings = (
        ClinicalConversationBinding.objects.filter(
            doctor=doctor,
            hospital_id=doctor.staff_membership.hospital_id,
            thread__is_deleted=False,
            thread__member_id__isnull=False,
        )
        .order_by("-updated_at", "-thread_id")
        .values("thread__member_id", "service_status", "doctor_attention_level", "updated_at")
    )
    rows: dict[int, dict] = {}
    for item in bindings:
        member_id = int(item["thread__member_id"])
        row = rows.get(member_id)
        if row is None:
            # bindings 已按更新时间倒序，首条即该患者最近会话。
            row = {
                "member_id": member_id,
                "service_status": item["service_status"],
                "priority_patient": False,
                "latest_conversation_at": item["updated_at"],
                "conversation_count": 0,
            }
            rows[member_id] = row
        row["conversation_count"] += 1
        if (
            item["doctor_attention_level"] == ClinicalConversationBinding.AttentionLevel.PRIORITY
            and item["service_status"] != ClinicalConversationBinding.ServiceStatus.ENDED
        ):
            row["priority_patient"] = True
    return list(rows.values())
