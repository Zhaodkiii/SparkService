from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone

from chat_sync.models import ChatMessage, ChatMessageBlock
from file_manager.business_access import user_can_access_file
from file_manager.models import ManagedFile
from file_manager.url_utils import managed_file_download_url

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import ChatMessageAttribution, ClinicalConversationBinding, DoctorProfile
from hospital_care.services.audit import write_hospital_audit_log
from hospital_care.services.conversation_attachment_service import IMAGE_MIME_TYPES, attachment_limits
from hospital_care.services.conversation_service import assert_doctor_owns_binding
from hospital_care.services.sender import build_sender_snapshot


def resolve_message_attachments(*, user, attachments) -> tuple[list, list]:
    """校验并解析消息附件（DOCTOR-WORKSPACE-000004 第 16 问，医患共用）。

    支持常见医疗文档与图片（PDF/JPG/PNG，阈值配置化）；不信任客户端声明，
    以 ManagedFile 记录的真实 MIME/大小为准；文件必须对当前用户可访问
    （本人上传或已绑定到可见业务）。返回 (images, documents)。
    """
    limits = attachment_limits()
    items = [item for item in (attachments or []) if isinstance(item, dict)]
    if len(items) > limits["max_count"]:
        raise HospitalCareError(
            "ATTACHMENT_COUNT_LIMIT",
            details={"count": len(items), "max": limits["max_count"]},
        )
    images: list = []
    documents: list = []
    for order, item in enumerate(items):
        file_id = item.get("file_id")
        if file_id in (None, ""):
            raise HospitalCareError("PAYLOAD_INVALID", details={"field": "file_id"})
        managed = ManagedFile.objects.filter(id=file_id, is_deleted=False).first()
        if managed is None:
            raise HospitalCareError("ATTACHMENT_NOT_FOUND")
        if not user_can_access_file(user, managed):
            raise HospitalCareError("ATTACHMENT_NOT_FOUND")
        mime = (managed.mime_type or "").lower()
        if mime not in limits["allowed_mime_types"] and mime not in {"image/webp", "image/gif"}:
            raise HospitalCareError("ATTACHMENT_TYPE_UNSUPPORTED", details={"allowed": limits["allowed_mime_types"]})
        if managed.file_size and managed.file_size > limits["max_bytes"]:
            raise HospitalCareError("ATTACHMENT_SIZE_LIMIT", details={"max_bytes": limits["max_bytes"]})
        if mime in IMAGE_MIME_TYPES or mime in {"image/webp", "image/gif"}:
            images.append((order, managed))
        else:
            documents.append((order, managed))
    return images, documents


def send_doctor_message(*, request, doctor: DoctorProfile, thread_id, text: str, version: int | None, attachments=None) -> dict:
    content = (text or "").strip()
    images, documents = resolve_message_attachments(user=request.user, attachments=attachments) if attachments else ([], [])
    if not content and not images and not documents:
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

        metadata = {"hospital_actor": "doctor"}
        if images or documents:
            metadata["attachments"] = [
                {
                    # iOS 消息级 attachments 按 ChatAttachment 解码，id/type 必填
                    "id": str(managed.file_uuid),
                    "file_id": managed.id,
                    "type": "image",
                    "order": order,
                    "mime_type": managed.mime_type,
                    "file_size": managed.file_size,
                    "display_url": managed_file_download_url(managed),
                }
                for order, managed in images
            ] + [
                {
                    "id": str(managed.file_uuid),
                    "file_id": managed.id,
                    "type": "document",
                    "order": order,
                    "mime_type": managed.mime_type,
                    "file_size": managed.file_size,
                    "filename": managed.original_name,
                    "display_url": managed_file_download_url(managed),
                }
                for order, managed in documents
            ]
        message = ChatMessage.objects.create(
            user=thread.user,
            thread=thread,
            role=ChatMessage.Role.ASSISTANT,
            client_message_id=uuid.uuid4(),
            server_message_id=str(uuid.uuid4()),
            delivery_state=ChatMessage.DeliveryState.SENT,
            created_at=now,
            metadata=metadata,
        )
        if content:
            ChatMessageBlock.objects.create(
                id=uuid.uuid4(),
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
        if images:
            # imageGallery 采用 iOS 线上形态：_0 直接是图片数组
            ChatMessageBlock.objects.create(
                id=uuid.uuid4(),
                user=thread.user,
                thread=thread,
                message=message,
                kind="imageGallery",
                status=ChatMessageBlock.Status.READY,
                revision=1,
                order_key=1100,
                node_role="timeline",
                payload={
                    "image_gallery": {
                        # iOS 线上形态：_0 直接是图片数组；id/type 为 iOS ChatAttachment 必填字段
                        "_0": [
                            {
                                "id": str(managed.file_uuid),
                                "type": "image",
                                "file_id": managed.id,
                                "url": managed_file_download_url(managed),
                                "filename": managed.original_name,
                                "mime_type": managed.mime_type,
                                "order": order,
                            }
                            for order, managed in images
                        ]
                    }
                },
                created_at=now,
                updated_at=now,
            )
        if documents:
            # fileGallery 承载 PDF 等医疗文档；遵循 imageGallery 的 _0 数组形态。
            ChatMessageBlock.objects.create(
                id=uuid.uuid4(),
                user=thread.user,
                thread=thread,
                message=message,
                kind="fileGallery",
                status=ChatMessageBlock.Status.READY,
                revision=1,
                order_key=1200,
                node_role="timeline",
                payload={
                    "file_gallery": {
                        "_0": [
                            {
                                "id": str(managed.file_uuid),
                                "type": "document",
                                "file_id": managed.id,
                                "url": managed_file_download_url(managed),
                                "filename": managed.original_name,
                                "mime_type": managed.mime_type,
                                "file_size": managed.file_size,
                                "order": order,
                            }
                            for order, managed in documents
                        ]
                    }
                },
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
