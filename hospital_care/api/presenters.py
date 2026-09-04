from __future__ import annotations

from chat_sync.models import ChatMessage
from chat_sync.views import _to_payload

from file_manager.url_utils import managed_file_download_url
from hospital_care.models import (
    ChatMessageAttribution,
    ClinicalAgentProfile,
    ClinicalConversationBinding,
    DoctorProfile,
    Hospital,
    HospitalDepartment,
    HospitalKnowledgeBaseProfile,
    HospitalStaffMembership,
)
from hospital_care.services.sender import build_sender_snapshot
from medical.models import Member


def hospital_public(hospital: Hospital) -> dict:
    return {
        "id": str(hospital.id),
        "code": hospital.code,
        "name": hospital.name,
        "short_name": hospital.short_name,
        "grade": hospital.grade,
        "address": hospital.address,
        "service_phone": hospital.service_phone,
        "emergency_phone": hospital.emergency_phone,
        "website_url": hospital.website_url,
        "introduction": hospital.introduction,
        "service_mode": hospital.service_mode,
        "status": hospital.status,
        "province_code": hospital.province_code,
        "city_code": hospital.city_code,
        "district_code": hospital.district_code,
    }


def hospital_admin(hospital: Hospital, extra: dict | None = None) -> dict:
    payload = hospital_public(hospital)
    payload.update(
        {
            "registration_redirect_url": hospital.registration_redirect_url,
            "logo_file_id": hospital.logo_file_id,
            "version": hospital.version,
            "created_at": hospital.created_at.isoformat(),
            "updated_at": hospital.updated_at.isoformat(),
            "department_count": getattr(hospital, "department_count", None),
            "doctor_count": getattr(hospital, "doctor_count", None),
        }
    )
    if extra:
        payload.update(extra)
    return payload


def department_public(department: HospitalDepartment) -> dict:
    return {
        "id": str(department.id),
        "hospital_id": str(department.hospital_id),
        "parent_id": str(department.parent_id) if department.parent_id else None,
        "code": department.code,
        "name": department.name,
        "short_name": department.short_name,
        "description": department.description,
        "sort_order": department.sort_order,
        "status": department.status,
        "doctor_count": getattr(department, "doctor_count", None),
        "agent_count": getattr(department, "agent_count", None),
    }


def doctor_public(doctor: DoctorProfile) -> dict:
    avatar_file = getattr(doctor, "avatar_file", None)
    return {
        "id": str(doctor.id),
        "display_name": doctor.display_name,
        "title": doctor.title,
        "specialties": doctor.specialties or [],
        "introduction": doctor.introduction,
        "license_status": doctor.license_status,
        "profile_status": doctor.profile_status,
        "avatar_url": managed_file_download_url(avatar_file) if avatar_file is not None else "",
    }


def agent_public(agent: ClinicalAgentProfile, *, include_internal: bool = False) -> dict:
    from hospital_care.services.agent_avatar_service import resolve_agent_avatar

    resolved = resolve_agent_avatar(agent)
    payload = {
        "id": str(agent.id),
        "hospital_id": str(agent.hospital_id),
        "department": department_public(agent.department) if agent.department_id else None,
        "doctor": doctor_public(agent.doctor),
        "name": agent.name,
        "public_summary": agent.public_summary,
        "greeting": agent.greeting,
        "service_boundary": agent.service_boundary,
        "publication_status": agent.publication_status,
        "published_at": agent.published_at.isoformat() if agent.published_at else None,
        "avatar_source": agent.avatar_source,
        "avatar_url": resolved.url,
        "avatar_version": resolved.version,
    }
    if include_internal:
        binding = agent.scenario_binding
        payload.update(
            {
                "scenario_binding_id": agent.scenario_binding_id,
                "avatar_file_id": agent.avatar_file_id,
                "doctor_editable_policy": agent.doctor_editable_policy or {},
                "version": agent.version,
                "created_at": agent.created_at.isoformat() if getattr(agent, "created_at", None) else None,
                "updated_at": agent.updated_at.isoformat() if getattr(agent, "updated_at", None) else None,
                "binding": scenario_binding_public(binding) if binding is not None else None,
                "knowledge_bindings": knowledge_bindings_public(agent),
            }
        )
    return payload


def scenario_binding_public(binding) -> dict:
    model = getattr(binding, "model", None)
    return {
        "id": binding.id,
        "model": model.name if model is not None else "",
        "model_display_name": getattr(model, "display_name", "") if model is not None else "",
        "display_name": binding.display_name,
        "temperature": binding.temperature,
        "max_tokens": binding.max_tokens,
        "system_provision": binding.system_provision,
        "brief_description": binding.brief_description,
        "ai_tool_scenarios": binding.ai_tool_scenarios or [],
        "server_tool_scenarios": binding.server_tool_scenarios or [],
        "related_task_codes": binding.related_task_codes or [],
        "is_default": binding.is_default,
        "is_active": binding.is_active,
        "updated_at": binding.updated_at.isoformat() if binding.updated_at else None,
    }


def knowledge_bindings_public(agent: ClinicalAgentProfile) -> list[dict]:
    profile_map = {}
    knowledge_ids = [item.knowledge_base_id for item in agent.knowledge_bindings.all()]
    if knowledge_ids:
        profile_map = {
            str(item.knowledge_base_id): item
            for item in HospitalKnowledgeBaseProfile.objects.filter(knowledge_base_id__in=knowledge_ids)
        }
    rows = []
    for item in sorted(agent.knowledge_bindings.all(), key=lambda row: (row.sort_order, str(row.id))):
        profile = profile_map.get(str(item.knowledge_base_id))
        rows.append(
            {
                "knowledge_base_id": str(item.knowledge_base_id),
                "profile_id": str(profile.id) if profile else None,
                "name": profile.name if profile else "",
                "usage_scope": item.usage_scope,
                "status": item.status,
                "sort_order": item.sort_order,
            }
        )
    return rows


def knowledge_base_public(profile: HospitalKnowledgeBaseProfile, extra: dict | None = None) -> dict:
    payload = {
        "id": str(profile.id),
        "hospital_id": str(profile.hospital_id),
        "knowledge_base_id": str(profile.knowledge_base_id),
        "name": profile.name,
        "description": profile.description,
        "vector_status": profile.vector_status,
        "indexed_revision": profile.indexed_revision,
        "revision": getattr(profile, "revision", None),
        "embedding_binding_id": profile.embedding_binding_id,
        "department_ids": [str(link.department_id) for link in profile.department_links.all()],
        "departments": [department_public(link.department) for link in profile.department_links.all() if getattr(link, "department", None)],
        "document_count": getattr(profile, "document_count", None),
        "agent_count": getattr(profile, "agent_count", None),
        "version": profile.version,
        "created_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat(),
    }
    if extra:
        payload.update(extra)
    return payload


def knowledge_document_public(document) -> dict:
    return {
        "id": str(document.id),
        "title": document.title,
        "content": document.content,
        "excerpt": document.excerpt,
        "revision": document.revision,
        "updated_at": document.server_updated_at.isoformat() if document.server_updated_at else None,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }


def embedding_binding_option(binding) -> dict:
    model = getattr(binding, "model", None)
    return {
        "id": binding.id,
        "display_name": binding.display_name or (model.display_name if model else binding.model_id),
        "model": model.name if model else "",
        "is_default": binding.is_default,
        "is_active": binding.is_active,
    }


def catalog_model_option(model) -> dict:
    return {
        "name": model.name,
        "display_name": model.display_name,
        "company": model.company,
    }


def conversation_public(binding: ClinicalConversationBinding, *, for_doctor: bool = False) -> dict:
    thread = binding.thread
    member = Member.all_objects.filter(pk=thread.member_id).first() if thread.member_id else None
    payload = {
        "thread_id": str(thread.id),
        "hospital": hospital_public(binding.hospital),
        "department": department_public(binding.department),
        "doctor": doctor_public(binding.doctor),
        "agent": {
            "id": str(binding.agent_id),
            "name": binding.agent.name,
            "publication_status": binding.agent.publication_status,
        },
        "member_id": thread.member_id,
        "patient_display_name": member.name if member else "患者",
        "service_status": binding.service_status,
        "doctor_attention_level": binding.doctor_attention_level,
        "risk_signal_level": binding.risk_signal_level,
        "assigned_at": binding.assigned_at.isoformat() if binding.assigned_at else None,
        "doctor_joined_at": binding.doctor_joined_at.isoformat() if binding.doctor_joined_at else None,
        "ended_at": binding.ended_at.isoformat() if binding.ended_at else None,
        "end_reason": binding.end_reason if for_doctor else "",
        "version": binding.version,
        "updated_at": binding.updated_at.isoformat(),
        "title": thread.title,
        "unread_count": 0,
    }
    if for_doctor:
        payload["attention_note"] = binding.attention_note
    return payload


def serialize_message(message: ChatMessage, binding: ClinicalConversationBinding | None) -> dict:
    payload = _to_payload(message)
    attribution = getattr(message, "hospital_attribution", None)
    if attribution is None:
        try:
            attribution = message.hospital_attribution
        except ChatMessageAttribution.DoesNotExist:
            attribution = None
    payload["sender"] = build_sender_snapshot(attribution=attribution, binding=binding)
    payload["actor_type"] = attribution.actor_type if attribution else None
    return payload


def _optional_doctor(membership: HospitalStaffMembership):
    try:
        return membership.doctor_profile
    except DoctorProfile.DoesNotExist:
        return None


def staff_admin(membership: HospitalStaffMembership) -> dict:
    doctor = _optional_doctor(membership)
    return {
        "id": str(membership.id),
        "user_id": membership.user_id,
        "username": membership.user.username,
        "role": membership.role,
        "employee_no": membership.employee_no,
        "status": membership.status,
        "display_name": doctor.display_name if doctor else membership.user.get_full_name() or membership.user.username,
        "license_status": doctor.license_status if doctor else "",
    }


def staff_me(membership: HospitalStaffMembership) -> dict:
    doctor = _optional_doctor(membership)
    return {
        "hospital": hospital_public(membership.hospital),
        "membership": {
            "id": str(membership.id),
            "role": membership.role,
            "status": membership.status,
            "employee_no": membership.employee_no,
        },
        "doctor": doctor_public(doctor) if doctor else None,
    }
