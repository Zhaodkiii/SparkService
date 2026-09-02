from __future__ import annotations

from django.db.models import OuterRef, Q, QuerySet, Subquery

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    ClinicalAgentProfile,
    ClinicalConversationBinding,
    Hospital,
    HospitalDepartment,
)
from medical.services.member_binding_service import accessible_member_ids


def active_hospitals() -> QuerySet[Hospital]:
    return Hospital.objects.filter(status=Hospital.Status.ACTIVE)


def get_active_hospital(hospital_id) -> Hospital:
    hospital = active_hospitals().filter(pk=hospital_id).first()
    if hospital is None:
        raise HospitalCareError("HOSPITAL_NOT_FOUND")
    return hospital


def active_departments(hospital_id) -> QuerySet[HospitalDepartment]:
    return HospitalDepartment.objects.filter(
        hospital_id=hospital_id,
        hospital__status=Hospital.Status.ACTIVE,
        status=HospitalDepartment.Status.ACTIVE,
    ).order_by("sort_order", "name")


def _published_agent_filters(*, hospital_id=None, department_id=None, keyword: str = "") -> Q:
    filters = Q(
        hospital__status=Hospital.Status.ACTIVE,
        department__status=HospitalDepartment.Status.ACTIVE,
        publication_status=ClinicalAgentProfile.PublicationStatus.PUBLISHED,
        doctor__profile_status="active",
    )
    if hospital_id is not None:
        filters &= Q(hospital_id=hospital_id)
    if department_id:
        filters &= Q(department_id=department_id)
    if keyword:
        filters &= (
            Q(name__icontains=keyword)
            | Q(doctor__display_name__icontains=keyword)
            | Q(doctor__title__icontains=keyword)
            | Q(department__name__icontains=keyword)
        )
    return filters


def published_agents(*, hospital_id, department_id=None, keyword: str = "") -> QuerySet[ClinicalAgentProfile]:
    """Return one latest published agent per doctor for the patient directory."""
    filters = _published_agent_filters(hospital_id=hospital_id, department_id=department_id, keyword=keyword)
    latest_id = (
        ClinicalAgentProfile.objects.filter(filters)
        .filter(doctor_id=OuterRef("doctor_id"))
        .order_by("-published_at", "-updated_at", "-id")
        .values("pk")[:1]
    )
    return (
        ClinicalAgentProfile.objects.select_related("doctor", "doctor__avatar_file", "department", "hospital")
        .filter(filters)
        .filter(pk=Subquery(latest_id))
        .order_by("department__sort_order", "name")
    )


def get_published_agent(agent_id) -> ClinicalAgentProfile:
    agent = published_agents_unscoped().filter(pk=agent_id).first()
    if agent is None:
        raise HospitalCareError("AGENT_NOT_PUBLISHED")
    return agent


def published_agents_unscoped() -> QuerySet[ClinicalAgentProfile]:
    return ClinicalAgentProfile.objects.select_related("doctor", "doctor__avatar_file", "department", "hospital").filter(
        _published_agent_filters()
    )


def latest_conversation_for_agent(*, user, member_id: int, agent_id) -> ClinicalConversationBinding | None:
    return patient_conversations(user=user, member_id=member_id).filter(agent_id=agent_id).first()


def patient_conversations(*, user, member_id: int | None = None) -> QuerySet[ClinicalConversationBinding]:
    allowed_members = accessible_member_ids(user)
    qs = ClinicalConversationBinding.objects.select_related(
        "thread", "hospital", "department", "doctor", "agent"
    ).filter(thread__user=user, thread__is_deleted=False)
    if member_id is not None:
        if int(member_id) not in allowed_members:
            raise HospitalCareError("MEMBER_ACCESS_DENIED")
        qs = qs.filter(thread__member_id=int(member_id))
    else:
        qs = qs.filter(thread__member_id__in=allowed_members)
    return qs.order_by("-updated_at")


def get_patient_conversation(*, user, thread_id, member_id: int | None = None) -> ClinicalConversationBinding:
    qs = patient_conversations(user=user, member_id=member_id)
    binding = qs.filter(thread_id=thread_id).first()
    if binding is None:
        raise HospitalCareError("CONVERSATION_NOT_FOUND")
    return binding
