from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from ai_config.models import AIScenarioModelBinding
from chat_sync.ai_models.knowledge import KnowledgeBase

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import ClinicalAgentKnowledgeBinding, ClinicalAgentProfile, DoctorProfile, HospitalDepartment
from hospital_care.services.audit import write_hospital_audit_log


def _lock_agent(agent_id) -> ClinicalAgentProfile:
    agent = (
        ClinicalAgentProfile.objects.select_for_update()
        .select_related("hospital", "doctor", "doctor__staff_membership", "department", "scenario_binding")
        .filter(pk=agent_id)
        .first()
    )
    if agent is None:
        raise HospitalCareError("AGENT_NOT_FOUND")
    return agent


def _assert_version(agent: ClinicalAgentProfile, version: int | None):
    if version is None:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "version"})
    if int(version) != agent.version:
        raise HospitalCareError("AGENT_VERSION_CONFLICT", details={"version": agent.version})


def _assert_publish_ready(agent: ClinicalAgentProfile):
    doctor = agent.doctor
    if doctor.profile_status != DoctorProfile.ProfileStatus.ACTIVE:
        raise HospitalCareError("DOCTOR_PROFILE_NOT_ACTIVE")
    if agent.department.hospital_id != agent.hospital_id:
        raise HospitalCareError("DEPARTMENT_PARENT_INVALID")
    if not agent.scenario_binding_id or not agent.scenario_binding.is_active:
        raise HospitalCareError("AGENT_REVIEW_INVALID", details={"field": "scenario_binding"})
    if not (agent.service_boundary or "").strip():
        raise HospitalCareError("AGENT_REVIEW_INVALID", details={"field": "service_boundary"})


def upsert_doctor_agent(*, request, doctor: DoctorProfile, payload: dict) -> ClinicalAgentProfile:
    agent = ClinicalAgentProfile.objects.filter(doctor=doctor).order_by("-updated_at").first()
    editable = {
        "name": payload.get("name"),
        "public_summary": payload.get("public_summary"),
        "greeting": payload.get("greeting"),
        "service_boundary": payload.get("service_boundary"),
    }
    if agent is None:
        department_id = payload.get("department_id")
        department = HospitalDepartment.objects.filter(
            pk=department_id,
            hospital_id=doctor.staff_membership.hospital_id,
        ).first()
        if department is None:
            raise HospitalCareError("DEPARTMENT_NOT_FOUND")
        scenario = AIScenarioModelBinding.objects.filter(pk=payload.get("scenario_binding_id"), is_active=True).first()
        if scenario is None:
            raise HospitalCareError("PAYLOAD_INVALID", details={"field": "scenario_binding_id"})
        agent = ClinicalAgentProfile.objects.create(
            hospital=doctor.staff_membership.hospital,
            doctor=doctor,
            department=department,
            scenario_binding=scenario,
            name=(editable["name"] or f"{doctor.display_name} AI 助手").strip(),
            public_summary=editable["public_summary"] or "",
            greeting=editable["greeting"] or "",
            service_boundary=editable["service_boundary"] or "",
            publication_status=ClinicalAgentProfile.PublicationStatus.DRAFT,
        )
    else:
        for field, value in editable.items():
            if value is not None:
                setattr(agent, field, value)
        if agent.publication_status == ClinicalAgentProfile.PublicationStatus.PUBLISHED:
            agent.publication_status = ClinicalAgentProfile.PublicationStatus.REVIEW
        agent.version += 1
        agent.save()
    return agent


def submit_agent_for_review(*, request, doctor: DoctorProfile, version: int | None) -> ClinicalAgentProfile:
    with transaction.atomic():
        agent = ClinicalAgentProfile.objects.select_for_update().filter(doctor=doctor).order_by("-updated_at").first()
        if agent is None:
            raise HospitalCareError("AGENT_NOT_FOUND")
        _assert_version(agent, version)
        _assert_publish_ready(agent)
        agent.publication_status = ClinicalAgentProfile.PublicationStatus.REVIEW
        agent.version += 1
        agent.save(update_fields=["publication_status", "version", "updated_at"])
    return agent


def review_agent(*, request, agent_id, payload: dict) -> ClinicalAgentProfile:
    action = payload.get("action")
    if action not in {"publish", "reject", "disable"}:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "action"})
    if action in {"reject", "disable"} and not (payload.get("reason") or "").strip():
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "reason"})
    with transaction.atomic():
        agent = _lock_agent(agent_id)
        _assert_version(agent, payload.get("version"))
        if action == "publish":
            _assert_publish_ready(agent)
            agent.publication_status = ClinicalAgentProfile.PublicationStatus.PUBLISHED
            agent.published_at = timezone.now()
        elif action == "reject":
            agent.publication_status = ClinicalAgentProfile.PublicationStatus.DRAFT
        else:
            agent.publication_status = ClinicalAgentProfile.PublicationStatus.DISABLED
        agent.version += 1
        agent.save()
    write_hospital_audit_log(
        request,
        action="hospital.agent.publish" if action == "publish" else "hospital.agent.disable",
        resource_type="clinical_agent",
        resource_id=str(agent.id),
        extra={
            "hospital_id": str(agent.hospital_id),
            "agent_id": str(agent.id),
            "publication_status": agent.publication_status,
            "review_action": action,
            "reason": payload.get("reason") or "",
            "version": agent.version,
        },
    )
    return agent


def bind_knowledge(*, request, agent_id, knowledge_base_id, owner_user_id, usage_scope: str | None = None) -> ClinicalAgentKnowledgeBinding:
    agent = ClinicalAgentProfile.objects.filter(pk=agent_id).first()
    if agent is None:
        raise HospitalCareError("AGENT_NOT_FOUND")
    knowledge_base = KnowledgeBase.objects.filter(pk=knowledge_base_id, user_id=owner_user_id, is_deleted=False).first()
    if knowledge_base is None:
        raise HospitalCareError("KNOWLEDGE_BASE_FORBIDDEN")
    binding, _ = ClinicalAgentKnowledgeBinding.objects.get_or_create(
        agent=agent,
        knowledge_base=knowledge_base,
        defaults={
            "usage_scope": usage_scope or ClinicalAgentKnowledgeBinding.UsageScope.DOCTOR,
            "status": ClinicalAgentKnowledgeBinding.Status.ACTIVE,
            "approved_by": getattr(request, "user", None),
            "approved_at": timezone.now(),
        },
    )
    return binding
