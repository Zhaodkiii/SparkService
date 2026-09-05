"""DOCTOR-WORKSPACE-000004 第 16/33 问：医生问诊附件上传与校验。

- 附件直接归属消息，消息通过 thread_id 归属问诊；文件本体复用 ManagedFile。
- 上传绑定当前 thread_id 与当前医生权限；已结束/非本人问诊拒绝。
- 服务端同时校验 MIME、扩展名、大小与文件内容（图片用 Pillow 解码，PDF 校验文件头）。
- 上传成功即绑定 business_type="hospital_conversation" + business_id=thread_id，
  患者侧经成员绑定鉴权读取，权限边界与问诊一致。
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from io import BytesIO

from django.conf import settings
from django.utils import timezone
from PIL import Image

from file_manager.business_relations import bind_file_to_business
from file_manager.models import ManagedFile
from file_manager.services.oss_object_service import OssUploadError, put_bytes
from file_manager.url_utils import managed_file_download_url

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import ClinicalConversationBinding, DoctorProfile
from hospital_care.services.audit import write_hospital_audit_log

logger = logging.getLogger("hospital_care.conversation_attachment")

CONVERSATION_ATTACHMENT_BUSINESS_TYPE = "hospital_conversation"

_OBJECT_KEY_PREFIX = "zhaodkdream/spark_service/hospital/attachment"

_MIME_EXT = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
}

_PIL_FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
}

IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}


def attachment_limits() -> dict:
    return {
        "max_bytes": int(getattr(settings, "HOSPITAL_DOCTOR_ATTACHMENT_MAX_BYTES", 20 * 1024 * 1024)),
        "max_count": int(getattr(settings, "HOSPITAL_DOCTOR_ATTACHMENT_MAX_COUNT", 5)),
        "allowed_mime_types": sorted(
            getattr(
                settings,
                "HOSPITAL_DOCTOR_ATTACHMENT_ALLOWED_MIME_TYPES",
                {"application/pdf", "image/jpeg", "image/png"},
            )
        ),
    }


def _real_mime(raw: bytes, declared_mime: str) -> str | None:
    """按文件内容校验真实类型；返回规范化 MIME，校验失败返回 None。"""
    if not raw:
        return None
    if declared_mime == "application/pdf":
        return "application/pdf" if raw[:5] == b"%PDF-" else None
    if declared_mime in IMAGE_MIME_TYPES:
        try:
            with Image.open(BytesIO(raw)) as image:
                detected = image.format
                image.verify()
            with Image.open(BytesIO(raw)) as image:
                image.load()
        except Exception:
            return None
        return _PIL_FORMAT_TO_MIME.get(detected or "")
    return None


def _lock_owned_binding(*, doctor: DoctorProfile, thread_id) -> ClinicalConversationBinding:
    binding = (
        ClinicalConversationBinding.objects.select_related("thread")
        .filter(
            doctor=doctor,
            hospital_id=doctor.staff_membership.hospital_id,
            thread__is_deleted=False,
            thread_id=thread_id,
        )
        .first()
    )
    if binding is None:
        raise HospitalCareError("CONVERSATION_NOT_ASSIGNED")
    if binding.service_status == ClinicalConversationBinding.ServiceStatus.ENDED:
        raise HospitalCareError("CONVERSATION_ENDED")
    return binding


def list_conversation_attachments(binding: ClinicalConversationBinding) -> list[dict]:
    """DOCTOR-WORKSPACE-000004：当前问诊的病历与附件清单（只读）。

    附件直接归属消息（imageGallery/fileGallery 块），按消息时间正序返回；
    URL 沿用 ManagedFile 下载链接，不包含存储路径等内部信息。
    """
    from chat_sync.models import ChatMessageBlock

    blocks = (
        ChatMessageBlock.objects.filter(
            thread_id=binding.thread_id,
            kind__in=["imageGallery", "fileGallery", "fileAttachments"],
            message__tombstone=False,
        )
        .select_related("message")
        .order_by("message__created_at", "message__id", "order_key")
    )
    items: list[dict] = []
    for block in blocks:
        payload = block.payload or {}
        for key in ("image_gallery", "file_gallery", "file_attachments"):
            gallery = payload.get(key)
            if not isinstance(gallery, dict):
                continue
            for value in gallery.values():
                if not isinstance(value, list):
                    continue
                for entry in value:
                    if not isinstance(entry, dict):
                        continue
                    items.append(
                        {
                            "file_id": entry.get("file_id"),
                            "filename": entry.get("filename") or entry.get("name") or "附件",
                            "mime_type": entry.get("mime_type") or "",
                            "file_size": entry.get("file_size"),
                            "url": entry.get("url") or "",
                            "kind": "image" if key == "image_gallery" else "document",
                            "message_id": block.message_id,
                            "created_at": block.message.created_at.isoformat() if block.message else None,
                        }
                    )
    return items


def upload_conversation_attachment(*, request, doctor: DoctorProfile, thread_id, uploaded) -> dict:
    """医生上传当前问诊附件；返回可用于发消息的 file_id 与展示信息。"""
    binding = _lock_owned_binding(doctor=doctor, thread_id=thread_id)
    limits = attachment_limits()

    if uploaded is None:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "file"})
    if uploaded.size is not None and int(uploaded.size) > limits["max_bytes"]:
        raise HospitalCareError(
            "ATTACHMENT_SIZE_LIMIT",
            details={"max_bytes": limits["max_bytes"]},
        )
    raw = uploaded.read()
    if not raw:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "file"})
    if len(raw) > limits["max_bytes"]:
        raise HospitalCareError(
            "ATTACHMENT_SIZE_LIMIT",
            details={"max_bytes": limits["max_bytes"]},
        )

    declared_mime = (getattr(uploaded, "content_type", "") or "").strip().lower()
    original_name = (getattr(uploaded, "name", "") or "attachment").rsplit("/", 1)[-1][:255] or "attachment"
    ext = (original_name.rsplit(".", 1)[-1].lower() if "." in original_name else "")
    if declared_mime not in _MIME_EXT or _MIME_EXT[declared_mime] != ext:
        raise HospitalCareError(
            "ATTACHMENT_TYPE_UNSUPPORTED",
            details={"allowed": limits["allowed_mime_types"]},
        )
    real_mime = _real_mime(raw, declared_mime)
    if real_mime is None:
        raise HospitalCareError(
            "ATTACHMENT_TYPE_UNSUPPORTED",
            details={"allowed": limits["allowed_mime_types"]},
        )

    file_uuid = uuid.uuid4()
    object_key = f"{_OBJECT_KEY_PREFIX}/{file_uuid.hex}.{_MIME_EXT[real_mime]}"
    try:
        put_bytes(object_key=object_key, content=raw, content_type=real_mime)
    except OssUploadError as exc:
        logger.warning("问诊附件 OSS 上传失败: %s", type(exc).__name__)
        raise HospitalCareError("ATTACHMENT_UPLOAD_FAILED") from exc

    file_record = ManagedFile.objects.create(
        user=request.user,
        file_uuid=file_uuid,
        file_path="",
        original_name=original_name,
        file_ext=_MIME_EXT[real_mime],
        mime_type=real_mime,
        file_size=len(raw),
        file_md5=hashlib.md5(raw).hexdigest(),
        is_public=True,
        object_key=object_key,
        storage_type="oss",
    )
    bind_file_to_business(request.user, file_record, CONVERSATION_ATTACHMENT_BUSINESS_TYPE, str(binding.thread_id))

    write_hospital_audit_log(
        request,
        action="hospital.conversation_attachment.upload",
        resource_type="hospital_conversation_attachment",
        resource_id=str(file_record.id),
        extra={
            "hospital_id": str(binding.hospital_id),
            "doctor_id": str(doctor.id),
            "thread_id": str(binding.thread_id),
            "file_id": str(file_record.id),
        },
    )
    return {
        "file_id": file_record.id,
        "file_uuid": str(file_record.file_uuid),
        "original_name": file_record.original_name,
        "mime_type": file_record.mime_type,
        "file_size": file_record.file_size,
        "display_url": managed_file_download_url(file_record),
        "uploaded_at": timezone.now().isoformat(),
    }
