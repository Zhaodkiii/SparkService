from __future__ import annotations

from django.db.models import Count, Q, QuerySet

from backoffice.models import AdminAuditLog
from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    ClinicalAgentProfile,
    ClinicalConversationBinding,
    DoctorProfile,
    Hospital,
    HospitalDepartment,
    HospitalStaffMembership,
)


def hospital_queryset(*, q: str = "", status: str = "", service_mode: str = "") -> QuerySet[Hospital]:
    qs = Hospital.objects.all().annotate(
        department_count=Count("departments", distinct=True),
        doctor_count=Count(
            "staff_memberships",
            filter=Q(staff_memberships__role=HospitalStaffMembership.Role.DOCTOR),
            distinct=True,
        ),
    )
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(short_name__icontains=q))
    if status:
        qs = qs.filter(status=status)
    if service_mode:
        qs = qs.filter(service_mode=service_mode)
    return qs.order_by("-updated_at")


def hospital_status_counts() -> dict[str, int]:
    base = Hospital.objects.all()
    return {
        "total": base.count(),
        "active": base.filter(status=Hospital.Status.ACTIVE).count(),
        "draft": base.filter(status=Hospital.Status.DRAFT).count(),
        "suspended": base.filter(status=Hospital.Status.SUSPENDED).count(),
    }


def get_hospital(hospital_id) -> Hospital:
    hospital = Hospital.objects.filter(pk=hospital_id).first()
    if hospital is None:
        raise HospitalCareError("HOSPITAL_NOT_FOUND")
    return hospital


def hospital_overview(hospital: Hospital) -> dict:
    return {
        "department_count": HospitalDepartment.objects.filter(hospital=hospital).count(),
        "doctor_count": DoctorProfile.objects.filter(staff_membership__hospital=hospital).count(),
        "published_agent_count": ClinicalAgentProfile.objects.filter(
            hospital=hospital,
            publication_status=ClinicalAgentProfile.PublicationStatus.PUBLISHED,
        ).count(),
        "active_conversation_count": ClinicalConversationBinding.objects.filter(
            hospital=hospital,
        )
        .exclude(service_status=ClinicalConversationBinding.ServiceStatus.ENDED)
        .count(),
        "pending_license_count": DoctorProfile.objects.filter(
            staff_membership__hospital=hospital,
            license_status=DoctorProfile.LicenseStatus.UNVERIFIED,
        ).count(),
        "pending_review_agent_count": ClinicalAgentProfile.objects.filter(
            hospital=hospital,
            publication_status=ClinicalAgentProfile.PublicationStatus.REVIEW,
        ).count(),
    }


def hospital_departments(hospital_id, *, q: str = "", status: str = "") -> QuerySet[HospitalDepartment]:
    qs = HospitalDepartment.objects.filter(hospital_id=hospital_id).annotate(
        doctor_count=Count("doctor_memberships", distinct=True),
        agent_count=Count("clinical_agents", distinct=True),
    )
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    if status:
        qs = qs.filter(status=status)
    return qs.order_by("sort_order", "name")


def hospital_staff(hospital_id, *, q: str = "") -> QuerySet[HospitalStaffMembership]:
    qs = HospitalStaffMembership.objects.select_related("user", "doctor_profile").filter(hospital_id=hospital_id)
    if q:
        qs = qs.filter(Q(user__username__icontains=q) | Q(employee_no__icontains=q) | Q(doctor_profile__display_name__icontains=q))
    return qs.order_by("-updated_at")


def hospital_doctors(hospital_id, *, q: str = "") -> QuerySet[DoctorProfile]:
    qs = DoctorProfile.objects.select_related("staff_membership", "staff_membership__user").filter(
        staff_membership__hospital_id=hospital_id
    )
    if q:
        qs = qs.filter(Q(display_name__icontains=q) | Q(title__icontains=q))
    return qs.order_by("-updated_at")


def hospital_agents(hospital_id, *, q: str = "", status: str = "", department_id=None) -> QuerySet[ClinicalAgentProfile]:
    qs = ClinicalAgentProfile.objects.select_related(
        "doctor", "doctor__avatar_file", "department", "scenario_binding", "avatar_file"
    ).prefetch_related(
        "knowledge_bindings"
    ).filter(hospital_id=hospital_id)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(doctor__display_name__icontains=q))
    if status:
        qs = qs.filter(publication_status=status)
    if department_id:
        qs = qs.filter(department_id=department_id)
    return qs.order_by("-updated_at")


def hospital_audit_logs(hospital_id, *, action: str = ""):
    qs = AdminAuditLog.objects.filter(
        resource_type__in={
            "hospital",
            "hospital_department",
            "hospital_staff",
            "doctor",
            "clinical_agent",
            "hospital_conversation",
            "hospital_message",
            "hospital_knowledge",
            "hospital_agent",
        }
    )
    hid = str(hospital_id)
    qs = qs.filter(
        Q(resource_id=hid)
        | Q(request_payload__hospital_id=hid)
        | Q(response_payload__resource_id=hid)
    )
    if action:
        qs = qs.filter(action=action)
    return qs.order_by("-created_at")
