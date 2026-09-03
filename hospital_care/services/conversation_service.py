from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone

from chat_sync.contracts.canonical import KIND_HOSPITAL_DOCTOR_INTRO_CARD, hospital_doctor_intro_card_payload
from chat_sync.models import ChatMessage, ChatMessageBlock, ChatThread
from file_manager.url_utils import managed_file_download_url
from medical.services.member_binding_service import ensure_can_access_member

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    ChatMessageAttribution,
    ClinicalAgentProfile,
    ClinicalConversationBinding,
    DoctorProfile,
    Hospital,
)
from hospital_care.services.audit import write_hospital_audit_log


ENDABLE_STATUSES = {
    ClinicalConversationBinding.ServiceStatus.AI_ACTIVE,
    ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR,
    ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED,
}


def _lock_binding(thread_id) -> ClinicalConversationBinding:
    binding = (
        ClinicalConversationBinding.objects.select_for_update()
        .select_related("thread", "hospital", "department", "doctor", "doctor__staff_membership", "agent")
        .filter(thread_id=thread_id)
        .first()
    )
    if binding is None:
        raise HospitalCareError("CONVERSATION_NOT_FOUND")
    return binding


def _assert_version(binding: ClinicalConversationBinding, version: int | None):
    if version is None:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "version"})
    if int(version) != binding.version:
        raise HospitalCareError("CONVERSATION_VERSION_CONFLICT", details={"version": binding.version})


def _create_system_message(
    *,
    thread: ChatThread,
    agent: ClinicalAgentProfile,
    text: str | None = None,
    actor_type: str,
    kind: str = "text",
    payload: dict | None = None,
) -> ChatMessage:
    now = timezone.now()
    message = ChatMessage.objects.create(
        user=thread.user,
        thread=thread,
        role=ChatMessage.Role.SYSTEM if actor_type == ChatMessageAttribution.ActorType.SYSTEM else ChatMessage.Role.ASSISTANT,
        client_message_id=uuid.uuid4(),
        server_message_id=str(uuid.uuid4()),
        delivery_state=ChatMessage.DeliveryState.SENT,
        created_at=now,
    )
    block_id = uuid.uuid4()
    ChatMessageBlock.objects.create(
        id=block_id,
        user=thread.user,
        thread=thread,
        message=message,
        kind=kind,
        status=ChatMessageBlock.Status.READY,
        revision=1,
        order_key=1000,
        node_role="timeline",
        payload=payload if payload is not None else {"text": {"_0": text or ""}},
        created_at=now,
        updated_at=now,
    )
    ChatMessageAttribution.objects.create(
        message=message,
        actor_type=actor_type,
        actor_user=None,
        doctor=None,
        agent=agent if actor_type == ChatMessageAttribution.ActorType.AI_AGENT else None,
        display_name_snapshot=agent.name if actor_type == ChatMessageAttribution.ActorType.AI_AGENT else "系统",
        source=ChatMessageAttribution.Source.SYSTEM,
    )
    return message


def _doctor_intro_snapshot(agent: ClinicalAgentProfile) -> dict:
    doctor = agent.doctor
    specialties = doctor.specialties if isinstance(doctor.specialties, list) else []
    avatar_file = getattr(doctor, "avatar_file", None)
    return {
        "doctor": {
            "display_name": doctor.display_name,
            "title": doctor.title or "",
            "hospital_name": agent.hospital.name,
            "department_name": agent.department.name if agent.department_id else "",
            "avatar_url": managed_file_download_url(avatar_file) if avatar_file is not None else "",
        },
        "agent": {
            "agent_id": str(agent.id),
            "agent_name": agent.name,
            "service_boundary": agent.service_boundary or "",
        },
        "professional_directions": [str(item) for item in specialties[:3]],
        "introduction_excerpt": (doctor.introduction or "")[:120],
        "detail_route": {"agent_id": str(agent.id)},
    }


def _create_doctor_intro_card(*, thread: ChatThread, agent: ClinicalAgentProfile) -> ChatMessage:
    existing = (
        ChatMessageBlock.objects.filter(thread=thread, kind=KIND_HOSPITAL_DOCTOR_INTRO_CARD)
        .select_related("message")
        .first()
    )
    if existing is not None:
        return existing.message
    return _create_system_message(
        thread=thread,
        agent=agent,
        actor_type=ChatMessageAttribution.ActorType.SYSTEM,
        kind=KIND_HOSPITAL_DOCTOR_INTRO_CARD,
        payload=hospital_doctor_intro_card_payload(_doctor_intro_snapshot(agent)),
    )


def create_patient_conversation(*, request, user, agent_id, member_id: int, thread_id=None) -> ClinicalConversationBinding:
    try:
        ensure_can_access_member(user=user, member_id=int(member_id))
    except PermissionError as exc:
        raise HospitalCareError("MEMBER_ACCESS_DENIED") from exc

    agent = (
        ClinicalAgentProfile.objects.select_related(
            "hospital", "department", "doctor", "doctor__staff_membership", "doctor__avatar_file"
        )
        .filter(pk=agent_id)
        .first()
    )
    if agent is None:
        raise HospitalCareError("AGENT_NOT_FOUND")
    if agent.publication_status != ClinicalAgentProfile.PublicationStatus.PUBLISHED:
        raise HospitalCareError("AGENT_NOT_PUBLISHED")
    if agent.hospital.status != Hospital.Status.ACTIVE:
        raise HospitalCareError("HOSPITAL_INACTIVE")

    client_thread_id = thread_id or uuid.uuid4()
    existing_thread = ChatThread.objects.filter(user=user, id=client_thread_id).first()
    if existing_thread is not None:
        existing_binding = ClinicalConversationBinding.objects.filter(thread=existing_thread).first()
        if existing_binding is not None:
            if existing_binding.hospital_id != agent.hospital_id:
                raise HospitalCareError("CONVERSATION_REBIND_FORBIDDEN")
            return existing_binding
        raise HospitalCareError("CONVERSATION_REBIND_FORBIDDEN")

    now = timezone.now()
    with transaction.atomic():
        thread = ChatThread.objects.create(
            id=client_thread_id,
            user=user,
            member_id=int(member_id),
            title=agent.name,
            role_prompt=agent.service_boundary,
        )
        binding = ClinicalConversationBinding.objects.create(
            thread=thread,
            hospital=agent.hospital,
            department=agent.department,
            doctor=agent.doctor,
            agent=agent,
            service_status=ClinicalConversationBinding.ServiceStatus.AI_ACTIVE,
            assigned_at=now,
        )
        _create_doctor_intro_card(thread=thread, agent=agent)
        disclaimer = (
            f"您正在咨询「{agent.name}」。本助手由{agent.doctor.display_name}团队维护，"
            "提供健康信息与就医指导，不构成诊断或处方。"
        )
        _create_system_message(
            thread=thread,
            agent=agent,
            text=disclaimer,
            actor_type=ChatMessageAttribution.ActorType.SYSTEM,
        )
    write_hospital_audit_log(
        request,
        action="hospital.conversation.create",
        resource_type="hospital_conversation",
        resource_id=str(thread.id),
        extra={
            "hospital_id": str(agent.hospital_id),
            "agent_id": str(agent.id),
            "thread_id": str(thread.id),
            "member_id": int(member_id),
        },
    )
    return binding


def assert_doctor_owns_binding(*, doctor: DoctorProfile, binding: ClinicalConversationBinding):
    if binding.doctor_id != doctor.id:
        raise HospitalCareError("CONVERSATION_NOT_ASSIGNED")


def join_conversation(*, request, doctor: DoctorProfile, thread_id, version: int | None) -> ClinicalConversationBinding:
    with transaction.atomic():
        binding = _lock_binding(thread_id)
        assert_doctor_owns_binding(doctor=doctor, binding=binding)
        _assert_version(binding, version)
        if binding.service_status == ClinicalConversationBinding.ServiceStatus.ENDED:
            raise HospitalCareError("CONVERSATION_ENDED")
        if binding.service_status != ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED:
            binding.service_status = ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED
            binding.doctor_joined_at = timezone.now()
            binding.version += 1
            binding.save(update_fields=["service_status", "doctor_joined_at", "version", "updated_at"])
            _create_system_message(
                thread=binding.thread,
                agent=binding.agent,
                text=f"{doctor.display_name}已接管本次会话",
                actor_type=ChatMessageAttribution.ActorType.SYSTEM,
            )
    write_hospital_audit_log(
        request,
        action="hospital.conversation.join",
        resource_type="hospital_conversation",
        resource_id=str(binding.thread_id),
        extra={"hospital_id": str(binding.hospital_id), "doctor_id": str(doctor.id), "thread_id": str(binding.thread_id)},
    )
    return binding


def leave_conversation(*, request, doctor: DoctorProfile, thread_id, version: int | None) -> ClinicalConversationBinding:
    """DOCTOR-WORKSPACE-000001 D-015/D-016：医生取消接管，恢复 AI 自动回复。"""
    with transaction.atomic():
        binding = _lock_binding(thread_id)
        assert_doctor_owns_binding(doctor=doctor, binding=binding)
        _assert_version(binding, version)
        if binding.service_status == ClinicalConversationBinding.ServiceStatus.ENDED:
            raise HospitalCareError("CONVERSATION_ENDED")
        if binding.service_status != ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED:
            raise HospitalCareError("CONVERSATION_NOT_JOINED")
        binding.service_status = ClinicalConversationBinding.ServiceStatus.AI_ACTIVE
        binding.version += 1
        binding.save(update_fields=["service_status", "version", "updated_at"])
        _create_system_message(
            thread=binding.thread,
            agent=binding.agent,
            text=f"{doctor.display_name}已取消接管，AI 恢复自动回复。",
            actor_type=ChatMessageAttribution.ActorType.SYSTEM,
        )
    write_hospital_audit_log(
        request,
        action="hospital.conversation.leave",
        resource_type="hospital_conversation",
        resource_id=str(binding.thread_id),
        extra={"hospital_id": str(binding.hospital_id), "doctor_id": str(doctor.id), "thread_id": str(binding.thread_id)},
    )
    return binding


def update_attention(*, request, doctor: DoctorProfile, thread_id, payload: dict) -> ClinicalConversationBinding:
    level = payload.get("doctor_attention_level") or payload.get("attention_level")
    if level not in ClinicalConversationBinding.AttentionLevel.values:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "doctor_attention_level"})
    with transaction.atomic():
        binding = _lock_binding(thread_id)
        assert_doctor_owns_binding(doctor=doctor, binding=binding)
        _assert_version(binding, payload.get("version"))
        if binding.service_status == ClinicalConversationBinding.ServiceStatus.ENDED:
            raise HospitalCareError("CONVERSATION_ENDED")
        binding.doctor_attention_level = level
        binding.attention_note = payload.get("attention_note") or binding.attention_note
        binding.version += 1
        binding.save(update_fields=["doctor_attention_level", "attention_note", "version", "updated_at"])
    write_hospital_audit_log(
        request,
        action="hospital.conversation.attention_update",
        resource_type="hospital_conversation",
        resource_id=str(binding.thread_id),
        extra={
            "hospital_id": str(binding.hospital_id),
            "thread_id": str(binding.thread_id),
            "doctor_attention_level": binding.doctor_attention_level,
        },
    )
    return binding


def end_conversation(*, request, doctor: DoctorProfile, thread_id, payload: dict) -> ClinicalConversationBinding:
    reason = (payload.get("end_reason") or payload.get("reason") or "").strip()
    if not reason:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "end_reason"})
    with transaction.atomic():
        binding = _lock_binding(thread_id)
        assert_doctor_owns_binding(doctor=doctor, binding=binding)
        _assert_version(binding, payload.get("version"))
        if binding.service_status == ClinicalConversationBinding.ServiceStatus.ENDED:
            return binding
        if binding.service_status not in ENDABLE_STATUSES:
            raise HospitalCareError("CONVERSATION_ENDED")
        binding.service_status = ClinicalConversationBinding.ServiceStatus.ENDED
        binding.ended_at = timezone.now()
        binding.ended_by = request.user
        binding.end_reason = reason
        binding.version += 1
        binding.save(
            update_fields=["service_status", "ended_at", "ended_by", "end_reason", "version", "updated_at"]
        )
        _create_system_message(
            thread=binding.thread,
            agent=binding.agent,
            text="本次服务已结束，历史消息仍可查看。",
            actor_type=ChatMessageAttribution.ActorType.SYSTEM,
        )
    write_hospital_audit_log(
        request,
        action="hospital.conversation.end",
        resource_type="hospital_conversation",
        resource_id=str(binding.thread_id),
        extra={
            "hospital_id": str(binding.hospital_id),
            "thread_id": str(binding.thread_id),
            "end_reason": reason,
            "service_status": binding.service_status,
        },
    )
    return binding
