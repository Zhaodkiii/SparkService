from __future__ import annotations

from file_manager.url_utils import managed_file_download_url
from hospital_care.models import ChatMessageAttribution, ClinicalConversationBinding


def build_sender_snapshot(*, attribution: ChatMessageAttribution | None, binding: ClinicalConversationBinding | None) -> dict:
    if attribution is None:
        return {}
    from hospital_care.services.agent_avatar_service import resolve_agent_avatar

    doctor = attribution.doctor
    agent = attribution.agent
    hospital = binding.hospital if binding else (doctor.staff_membership.hospital if doctor else None)
    department = binding.department if binding else None
    snapshot = {
        "actor_type": attribution.actor_type,
        "actor_id": str(attribution.actor_user_id or attribution.agent_id or ""),
        "display_name": attribution.display_name_snapshot,
        "avatar_url": "",
        "source": attribution.source,
    }
    if attribution.actor_type == ChatMessageAttribution.ActorType.DOCTOR and doctor:
        doctor_avatar_file = getattr(doctor, "avatar_file", None)
        doctor_avatar_url = managed_file_download_url(doctor_avatar_file) if doctor_avatar_file is not None else ""
        snapshot["avatar_url"] = doctor_avatar_url
        snapshot["doctor"] = {
            "doctor_id": str(doctor.id),
            "display_name": doctor.display_name,
            "title": doctor.title,
            "hospital_name": hospital.name if hospital else "",
            "department_name": department.name if department else "",
            "avatar_url": doctor_avatar_url,
            "verified": doctor.license_status == doctor.LicenseStatus.VERIFIED,
        }
    if attribution.actor_type == ChatMessageAttribution.ActorType.AI_AGENT and agent:
        resolved = resolve_agent_avatar(agent)
        snapshot["avatar_url"] = resolved.url
        snapshot["agent"] = {
            "agent_id": str(agent.id),
            "display_name": agent.name,
            "is_ai": True,
            "avatar_url": resolved.url,
        }
    return snapshot
