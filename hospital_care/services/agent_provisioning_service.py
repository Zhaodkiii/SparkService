from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ai_config.models import AIScenarioModelBinding, IdentityKind, ScenarioKey
from chat_sync.ai_runtime.tools.server_tool_config import prepare_server_tool_scenarios

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    ClinicalAgentKnowledgeBinding,
    ClinicalAgentProfile,
    DoctorProfile,
    Hospital,
    HospitalDepartment,
    HospitalKnowledgeBaseProfile,
    HospitalStaffMembership,
)
from hospital_care.services.ai_catalog import (
    assert_catalog_model_available,
    catalog_model_by_name,
    next_agent_binding_position,
)
from hospital_care.services.audit import write_hospital_audit_log


def _lock_hospital(hospital_id) -> Hospital:
    hospital = Hospital.objects.select_for_update().filter(pk=hospital_id).first()
    if hospital is None:
        raise HospitalCareError("HOSPITAL_NOT_FOUND")
    if hospital.status == Hospital.Status.SUSPENDED:
        raise HospitalCareError("HOSPITAL_INACTIVE")
    return hospital


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


def _assert_agent_version(agent: ClinicalAgentProfile, version) -> None:
    if version is None:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "version"})
    if int(version) != agent.version:
        raise HospitalCareError("AGENT_VERSION_CONFLICT", details={"version": agent.version})


def _resolve_active_doctor(hospital: Hospital, doctor_id) -> DoctorProfile:
    doctor = (
        DoctorProfile.objects.select_related("staff_membership")
        .filter(pk=doctor_id, staff_membership__hospital_id=hospital.id)
        .first()
    )
    if doctor is None:
        raise HospitalCareError("AGENT_DOCTOR_INVALID", details={"field": "doctor_id"})
    membership = doctor.staff_membership
    if membership.status != HospitalStaffMembership.Status.ACTIVE:
        raise HospitalCareError("AGENT_DOCTOR_INVALID", details={"field": "doctor_id", "reason": "membership"})
    if doctor.profile_status != DoctorProfile.ProfileStatus.ACTIVE:
        raise HospitalCareError("AGENT_DOCTOR_INVALID", details={"field": "doctor_id", "reason": "profile"})
    return doctor


def _resolve_active_department(hospital: Hospital, department_id) -> HospitalDepartment:
    department = HospitalDepartment.objects.filter(pk=department_id, hospital_id=hospital.id).first()
    if department is None or department.status != HospitalDepartment.Status.ACTIVE:
        raise HospitalCareError("AGENT_DEPARTMENT_INVALID", details={"field": "department_id"})
    return department


def _normalize_string_list(value, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": field_name})
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if raw is None:
            continue
        item = str(raw).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned


def _normalize_binding_payload(payload: dict | None) -> dict:
    data = payload or {}
    model_name = str(data.get("model") or "").strip()
    if not model_name:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "binding.model"})
    temperature = data.get("temperature", 0.2)
    max_tokens = data.get("max_tokens", 2048)
    try:
        temperature = float(temperature)
        max_tokens = int(max_tokens)
    except (TypeError, ValueError) as exc:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "binding"}) from exc
    ai_tools = _normalize_string_list(data.get("ai_tool_scenarios"), "binding.ai_tool_scenarios")
    names, error, offending = prepare_server_tool_scenarios(data.get("server_tool_scenarios") or [])
    if error:
        raise HospitalCareError(
            "PAYLOAD_INVALID",
            details={"field": "binding.server_tool_scenarios", "reason": error, "name": offending},
        )
    return {
        "model": catalog_model_by_name(model_name),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_provision": str(data.get("system_provision") or ""),
        "brief_description": str(data.get("brief_description") or ""),
        "ai_tool_scenarios": ai_tools,
        "server_tool_scenarios": names,
        "related_task_codes": _normalize_string_list(data.get("related_task_codes"), "binding.related_task_codes"),
        "display_name": str(data.get("display_name") or "").strip(),
    }


def _resolve_knowledge_profiles(hospital: Hospital, items: list | None) -> list[HospitalKnowledgeBaseProfile]:
    rows = items or []
    if not isinstance(rows, list):
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "knowledge_bases"})
    profiles: list[HospitalKnowledgeBaseProfile] = []
    seen: set[str] = set()
    for index, item in enumerate(rows):
        if isinstance(item, dict):
            profile_id = item.get("profile_id") or item.get("id")
        else:
            profile_id = item
        if not profile_id:
            raise HospitalCareError("PAYLOAD_INVALID", details={"field": f"knowledge_bases[{index}].profile_id"})
        key = str(profile_id)
        if key in seen:
            continue
        seen.add(key)
        profile = HospitalKnowledgeBaseProfile.objects.filter(
            pk=profile_id,
            hospital_id=hospital.id,
            is_deleted=False,
        ).first()
        if profile is None:
            raise HospitalCareError("HOSPITAL_KNOWLEDGE_NOT_FOUND", details={"profile_id": key})
        profiles.append(profile)
    return profiles


def _sync_knowledge_bindings(agent: ClinicalAgentProfile, profiles: list[HospitalKnowledgeBaseProfile], *, actor):
    desired_ids = [profile.knowledge_base_id for profile in profiles]
    existing = {str(item.knowledge_base_id): item for item in agent.knowledge_bindings.all()}
    desired_set = {str(kid) for kid in desired_ids}
    for knowledge_base_id, binding in existing.items():
        if knowledge_base_id not in desired_set:
            binding.delete()
    for sort_order, profile in enumerate(profiles):
        key = str(profile.knowledge_base_id)
        binding = existing.get(key)
        if binding is None:
            ClinicalAgentKnowledgeBinding.objects.create(
                agent=agent,
                knowledge_base_id=profile.knowledge_base_id,
                usage_scope=ClinicalAgentKnowledgeBinding.UsageScope.HOSPITAL,
                sort_order=sort_order,
                status=ClinicalAgentKnowledgeBinding.Status.ACTIVE,
                approved_by=actor,
            )
        elif binding.sort_order != sort_order or binding.status != ClinicalAgentKnowledgeBinding.Status.ACTIVE:
            binding.sort_order = sort_order
            binding.status = ClinicalAgentKnowledgeBinding.Status.ACTIVE
            binding.usage_scope = ClinicalAgentKnowledgeBinding.UsageScope.HOSPITAL
            binding.save(update_fields=["sort_order", "status", "usage_scope", "updated_at"])


def create_clinical_agent(*, request, hospital_id, payload: dict) -> ClinicalAgentProfile:
    with transaction.atomic():
        hospital = _lock_hospital(hospital_id)
        doctor = _resolve_active_doctor(hospital, payload.get("doctor_id"))
        department = _resolve_active_department(hospital, payload.get("department_id"))
        name = str(payload.get("name") or "").strip()
        if not name:
            raise HospitalCareError("PAYLOAD_INVALID", details={"field": "name"})
        binding_payload = _normalize_binding_payload(payload.get("binding"))
        assert_catalog_model_available(binding_payload["model"])
        profiles = _resolve_knowledge_profiles(hospital, payload.get("knowledge_bases"))
        binding = AIScenarioModelBinding.objects.create(
            scenario=ScenarioKey.CHAT,
            identity=IdentityKind.AGENT,
            model=binding_payload["model"],
            display_name=binding_payload["display_name"] or name,
            temperature=binding_payload["temperature"],
            max_tokens=binding_payload["max_tokens"],
            is_default=False,
            is_active=True,
            position=next_agent_binding_position(),
            system_provision=binding_payload["system_provision"],
            brief_description=binding_payload["brief_description"],
            ai_tool_scenarios=binding_payload["ai_tool_scenarios"],
            server_tool_scenarios=binding_payload["server_tool_scenarios"],
            related_task_codes=binding_payload["related_task_codes"],
        )
        agent = ClinicalAgentProfile.objects.create(
            hospital=hospital,
            doctor=doctor,
            department=department,
            scenario_binding=binding,
            name=name,
            public_summary=str(payload.get("public_summary") or ""),
            greeting=str(payload.get("greeting") or ""),
            service_boundary=str(payload.get("service_boundary") or ""),
            publication_status=ClinicalAgentProfile.PublicationStatus.DRAFT,
        )
        avatar_source = payload.get("avatar_source") or ClinicalAgentProfile.AvatarSource.DOCTOR
        if avatar_source == ClinicalAgentProfile.AvatarSource.CUSTOM:
            from hospital_care.services.agent_avatar_service import (
                bind_avatar_file_to_agent,
                resolve_valid_agent_avatar_file,
            )

            avatar_file = resolve_valid_agent_avatar_file(hospital=hospital, file_id=payload.get("avatar_file_id"))
            agent.avatar_source = ClinicalAgentProfile.AvatarSource.CUSTOM
            agent.avatar_file = avatar_file
            agent.save(update_fields=["avatar_source", "avatar_file", "updated_at"])
            bind_avatar_file_to_agent(file_record=avatar_file, agent=agent)
        elif avatar_source != ClinicalAgentProfile.AvatarSource.DOCTOR:
            raise HospitalCareError("AVATAR_SOURCE_INVALID", details={"field": "avatar_source"})
        _sync_knowledge_bindings(agent, profiles, actor=getattr(request, "user", None))
    write_hospital_audit_log(
        request,
        action="hospital.agent.create",
        resource_type="clinical_agent",
        resource_id=str(agent.id),
        extra={
            "hospital_id": str(hospital.id),
            "agent_id": str(agent.id),
            "doctor_id": str(doctor.id),
            "department_id": str(department.id),
            "binding_id": binding.id,
            "name": agent.name,
            "publication_status": agent.publication_status,
        },
    )
    write_hospital_audit_log(
        request,
        action="admin.ai.scenario_binding.create",
        resource_type="clinical_agent",
        resource_id=str(binding.id),
        extra={"hospital_id": str(hospital.id), "agent_id": str(agent.id), "binding_id": binding.id},
    )
    return agent


def _parse_binding_updated_at(value):
    if value is None:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "binding.updated_at"})
    if hasattr(value, "isoformat"):
        return value
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "binding.updated_at"})
    return parsed


def update_clinical_agent(*, request, agent_id, payload: dict) -> ClinicalAgentProfile:
    with transaction.atomic():
        agent = _lock_agent(agent_id)
        _assert_agent_version(agent, payload.get("version"))
        if agent.hospital.status == Hospital.Status.SUSPENDED:
            raise HospitalCareError("HOSPITAL_INACTIVE")
        if payload.get("department_id"):
            agent.department = _resolve_active_department(agent.hospital, payload.get("department_id"))
        for field in ("name", "public_summary", "greeting", "service_boundary"):
            if field in payload and payload[field] is not None:
                value = str(payload[field]).strip() if field == "name" else str(payload[field] or "")
                if field == "name" and not value:
                    raise HospitalCareError("PAYLOAD_INVALID", details={"field": "name"})
                setattr(agent, field, value)
        binding_data = payload.get("binding")
        if binding_data:
            current = agent.scenario_binding
            incoming = _parse_binding_updated_at(binding_data.get("updated_at"))
            current_ts = current.updated_at
            if timezone.is_naive(incoming) and timezone.is_aware(current_ts):
                incoming = timezone.make_aware(incoming, timezone.get_current_timezone())
            elif timezone.is_aware(incoming) and timezone.is_naive(current_ts):
                incoming = timezone.make_naive(incoming, timezone.get_current_timezone())
            if abs((incoming - current_ts).total_seconds()) > 0.001:
                raise HospitalCareError("AGENT_VERSION_CONFLICT", details={"field": "binding.updated_at"})
            writable = {}
            if "model" in binding_data and binding_data.get("model"):
                model = catalog_model_by_name(str(binding_data.get("model")))
                if model.id != current.model_id:
                    assert_catalog_model_available(model)
                    writable["model"] = model
            normalized = _normalize_binding_payload({**{
                "model": current.model.name,
                "temperature": current.temperature,
                "max_tokens": current.max_tokens,
                "system_provision": current.system_provision,
                "brief_description": current.brief_description,
                "ai_tool_scenarios": current.ai_tool_scenarios,
                "server_tool_scenarios": current.server_tool_scenarios,
                "related_task_codes": current.related_task_codes,
                "display_name": current.display_name,
            }, **{k: v for k, v in binding_data.items() if k != "updated_at" and v is not None}})
            current.temperature = normalized["temperature"]
            current.max_tokens = normalized["max_tokens"]
            current.system_provision = normalized["system_provision"]
            current.brief_description = normalized["brief_description"]
            current.ai_tool_scenarios = normalized["ai_tool_scenarios"]
            current.server_tool_scenarios = normalized["server_tool_scenarios"]
            current.related_task_codes = normalized["related_task_codes"]
            if writable.get("model") is not None:
                current.model = writable["model"]
            if binding_data.get("display_name") is not None:
                current.display_name = normalized["display_name"] or current.display_name
            current.save()
        if "knowledge_bases" in payload:
            profiles = _resolve_knowledge_profiles(agent.hospital, payload.get("knowledge_bases"))
            _sync_knowledge_bindings(agent, profiles, actor=getattr(request, "user", None))
        if agent.publication_status == ClinicalAgentProfile.PublicationStatus.PUBLISHED:
            agent.publication_status = ClinicalAgentProfile.PublicationStatus.REVIEW
        agent.version += 1
        agent.save()
    write_hospital_audit_log(
        request,
        action="hospital.agent.update",
        resource_type="clinical_agent",
        resource_id=str(agent.id),
        extra={
            "hospital_id": str(agent.hospital_id),
            "agent_id": str(agent.id),
            "binding_id": agent.scenario_binding_id,
            "name": agent.name,
            "publication_status": agent.publication_status,
            "version": agent.version,
        },
    )
    return agent
