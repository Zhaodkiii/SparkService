from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone

from chat_sync.models import ChatMessage, ChatMessageBlock

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import ChatMessageAttribution, ClinicalConversationBinding, DoctorProfile
from hospital_care.services.audit import write_hospital_audit_log
from hospital_care.services.conversation_service import assert_doctor_owns_binding
from hospital_care.services.sender import build_sender_snapshot


def send_doctor_message(*, request, doctor: DoctorProfile, thread_id, text: str, version: int | None) -> dict:
    content = (text or "").strip()
    if not content:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "text"})
    now = timezone.now()
    with transaction.atomic():
        binding = (
            ClinicalConversationBinding.objects.select_for_update()
            .select_related("thread", "hospital", "department", "doctor", "doctor__staff_membership", "agent")
            .filter(thread_id=thread_id)
            .first()
        )
        if binding is None:
            raise HospitalCareError("CONVERSATION_NOT_FOUND")
        assert_doctor_owns_binding(doctor=doctor, binding=binding)
        if version is not None and int(version) != binding.version:
            raise HospitalCareError("CONVERSATION_VERSION_CONFLICT", details={"version": binding.version})
        if binding.service_status == ClinicalConversationBinding.ServiceStatus.ENDED:
            raise HospitalCareError("CONVERSATION_ENDED")
        if binding.service_status != ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED:
            raise HospitalCareError("CONVERSATION_NOT_ASSIGNED", details={"service_status": binding.service_status})

        thread = binding.thread
        thread.updated_at = now
        thread.server_updated_at = now
        thread.save(update_fields=["updated_at", "server_updated_at"])

        message = ChatMessage.objects.create(
            user=thread.user,
            thread=thread,
            role=ChatMessage.Role.ASSISTANT,
            client_message_id=uuid.uuid4(),
            server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=now,
            metadata={"hospital_actor": "doctor"},
        )
        block_id = uuid.uuid4()
        ChatMessageBlock.objects.create(
            id=block_id,
            user=thread.user,
            thread=thread,
            message=message,
            kind="text",
            status=ChatMessageBlock.Status.READY,
            revision=1,
            order_key=1000,
            node_role="timeline",
            payload={"text": {"_0": content}},
            created_at=now,
            updated_at=now,
        )
        attribution = ChatMessageAttribution.objects.create(
            message=message,
            actor_type=ChatMessageAttribution.ActorType.DOCTOR,
            actor_user=request.user,
            doctor=doctor,
            agent=None,
            display_name_snapshot=f"{doctor.display_name} · 真人医生",
            source=ChatMessageAttribution.Source.DOCTOR_CONSOLE,
        )
        binding.version += 1
        binding.save(update_fields=["version", "updated_at"])

    write_hospital_audit_log(
        request,
        action="hospital.doctor_message.send",
        resource_type="hospital_message",
        resource_id=str(message.id),
        extra={
            "hospital_id": str(binding.hospital_id),
            "doctor_id": str(doctor.id),
            "thread_id": str(thread.id),
            "message_id": str(message.id),
        },
    )
    return {
        "message_id": message.id,
        "server_message_id": message.server_message_id,
        "client_message_id": str(message.client_message_id),
        "thread_id": str(thread.id),
        "role": message.role,
        "created_at": message.created_at.isoformat(),
        "sender": build_sender_snapshot(attribution=attribution, binding=binding),
        "version": binding.version,
    }
