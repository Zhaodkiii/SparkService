from __future__ import annotations

import re

from django.db.models import Case, IntegerField, QuerySet, When

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    ClinicalAgentProfile,
    ClinicalConversationBinding,
    DoctorProfile,
    HospitalStaffMembership,
)


def get_active_membership(*, user, hospital_id=None) -> HospitalStaffMembership:
    qs = HospitalStaffMembership.objects.select_related("hospital", "doctor_profile").filter(
        user=user,
        status=HospitalStaffMembership.Status.ACTIVE,
    )
    if hospital_id:
        qs = qs.filter(hospital_id=hospital_id)
    membership = qs.order_by("-updated_at").first()
    if membership is None:
        raise HospitalCareError("HOSPITAL_MEMBERSHIP_REQUIRED")
    return membership


def get_active_doctor(*, user, hospital_id=None) -> DoctorProfile:
    membership = get_active_membership(user=user, hospital_id=hospital_id)
    if membership.role != HospitalStaffMembership.Role.DOCTOR:
        raise HospitalCareError("DOCTOR_PROFILE_NOT_ACTIVE")
    doctor = (
        DoctorProfile.objects.select_related("staff_membership", "staff_membership__hospital")
        .filter(staff_membership=membership, profile_status=DoctorProfile.ProfileStatus.ACTIVE)
        .first()
    )
    if doctor is None:
        raise HospitalCareError("DOCTOR_PROFILE_NOT_ACTIVE")
    return doctor


_PATIENT_NUMBER_PATTERN = re.compile(r"^P?(\d{6,})$", re.IGNORECASE)


def _keyword_member_ids(keyword: str) -> set[int]:
    """DOCTOR-WORKSPACE-000004 第 21 问：搜索患者姓名与患者编号，不搜索消息正文。"""
    from medical.models import Member

    matched: set[int] = set()
    for member_id in Member.all_objects.filter(name__icontains=keyword, is_deleted=False).values_list("id", flat=True):
        matched.add(int(member_id))
    number_match = _PATIENT_NUMBER_PATTERN.match(keyword.strip())
    if number_match:
        matched.add(int(number_match.group(1)))
    return matched


def doctor_conversations(*, doctor: DoctorProfile, queue: str = "all", keyword: str = "") -> QuerySet[ClinicalConversationBinding]:
    qs = ClinicalConversationBinding.objects.select_related(
        "thread", "hospital", "department", "doctor", "agent"
    ).filter(
        doctor=doctor,
        hospital_id=doctor.staff_membership.hospital_id,
        thread__is_deleted=False,
    )
    if queue == "pending":
        qs = qs.filter(service_status=ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR)
    elif queue == "joined":
        qs = qs.filter(service_status=ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED)
    elif queue == "priority":
        qs = qs.filter(doctor_attention_level=ClinicalConversationBinding.AttentionLevel.PRIORITY).exclude(
            service_status=ClinicalConversationBinding.ServiceStatus.ENDED
        )
    elif queue == "ended":
        qs = qs.filter(service_status=ClinicalConversationBinding.ServiceStatus.ENDED)
    elif queue == "active":
        qs = qs.exclude(service_status=ClinicalConversationBinding.ServiceStatus.ENDED)
    if keyword:
        keyword = keyword.strip()
        member_ids = _keyword_member_ids(keyword)
        if member_ids:
            qs = qs.filter(thread__title__icontains=keyword) | qs.filter(thread__member_id__in=member_ids)
            qs = qs.distinct()
        else:
            qs = qs.filter(thread__title__icontains=keyword)
    # 第 22 问：重点优先，再按最近活动时间倒序，最后 thread_id 稳定键。
    return qs.annotate(
        _priority_rank=Case(
            When(doctor_attention_level=ClinicalConversationBinding.AttentionLevel.PRIORITY, then=0),
            default=1,
            output_field=IntegerField(),
        )
    ).order_by("_priority_rank", "-updated_at", "-thread_id")


def get_doctor_conversation(*, doctor: DoctorProfile, thread_id) -> ClinicalConversationBinding:
    binding = doctor_conversations(doctor=doctor).filter(thread_id=thread_id).first()
    if binding is None:
        raise HospitalCareError("CONVERSATION_NOT_ASSIGNED")
    return binding


def doctor_queue_counts(*, doctor: DoctorProfile) -> dict[str, int]:
    base = ClinicalConversationBinding.objects.filter(
        doctor=doctor,
        hospital_id=doctor.staff_membership.hospital_id,
        thread__is_deleted=False,
    )
    return {
        "all": base.count(),
        "pending": base.filter(service_status=ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR).count(),
        "joined": base.filter(service_status=ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED).count(),
        "priority": base.filter(doctor_attention_level=ClinicalConversationBinding.AttentionLevel.PRIORITY)
        .exclude(service_status=ClinicalConversationBinding.ServiceStatus.ENDED)
        .count(),
        "ended": base.filter(service_status=ClinicalConversationBinding.ServiceStatus.ENDED).count(),
    }


def doctor_agent(*, doctor: DoctorProfile) -> ClinicalAgentProfile | None:
    return (
        ClinicalAgentProfile.objects.select_related("department", "hospital", "avatar_file", "doctor__avatar_file")
        .filter(doctor=doctor)
        .order_by("-updated_at")
        .first()
    )
