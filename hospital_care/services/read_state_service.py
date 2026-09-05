"""DOCTOR-WORKSPACE-000004：医生-问诊已读游标与未读统计。

口径（第 19/20/31 问）：
- 问诊级未读数 = 该问诊中游标之后、归属为患者/AI 的可见消息数；
- 患者级未读总数 = 当前医生可见“未结束”问诊的问诊级未读之和；
- 进入问诊且消息成功加载后推进游标；游标只前进不回退；
- 已结束问诊不计入患者卡片未读总数，但仍保留问诊级未读计算。
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count

from chat_sync.models import ChatMessage
from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    ChatMessageAttribution,
    ClinicalConversationBinding,
    DoctorConversationReadCursor,
    DoctorProfile,
)
from hospital_care.services.audit import write_hospital_audit_log

# 计入医生未读的消息归属：患者与 AI；医生本人与系统消息不计数。
_UNREAD_ACTOR_TYPES = (
    ChatMessageAttribution.ActorType.PATIENT,
    ChatMessageAttribution.ActorType.AI_AGENT,
)


def _visible_thread_ids(*, doctor: DoctorProfile) -> list:
    return list(
        ClinicalConversationBinding.objects.filter(
            doctor=doctor,
            hospital_id=doctor.staff_membership.hospital_id,
            thread__is_deleted=False,
        ).values_list("thread_id", flat=True)
    )


def _cursors_by_thread(*, doctor: DoctorProfile, thread_ids: list) -> dict:
    cursors = DoctorConversationReadCursor.objects.filter(doctor=doctor, thread_id__in=thread_ids).values(
        "thread_id", "last_read_message_id"
    )
    return {row["thread_id"]: int(row["last_read_message_id"] or 0) for row in cursors}


def unread_counts_by_thread(*, doctor: DoctorProfile, thread_ids: list | None = None) -> dict:
    """按问诊返回未读消息数 {thread_id: unread_count}。"""
    if thread_ids is None:
        thread_ids = _visible_thread_ids(doctor=doctor)
    if not thread_ids:
        return {}
    cursor_map = _cursors_by_thread(doctor=doctor, thread_ids=thread_ids)
    rows = (
        ChatMessage.objects.filter(
            thread_id__in=thread_ids,
            tombstone=False,
            hospital_attribution__actor_type__in=_UNREAD_ACTOR_TYPES,
        )
        .values("thread_id", "id")
        .order_by("thread_id", "id")
    )
    counts = {thread_id: 0 for thread_id in thread_ids}
    for row in rows:
        if int(row["id"]) > cursor_map.get(row["thread_id"], 0):
            counts[row["thread_id"]] = counts.get(row["thread_id"], 0) + 1
    return counts


def unread_totals_by_member(*, doctor: DoctorProfile, exclude_ended: bool = True) -> dict:
    """按患者返回未结束问诊未读总数 {member_id: total_unread}。"""
    bindings = ClinicalConversationBinding.objects.filter(
        doctor=doctor,
        hospital_id=doctor.staff_membership.hospital_id,
        thread__is_deleted=False,
        thread__member_id__isnull=False,
    )
    if exclude_ended:
        bindings = bindings.exclude(service_status=ClinicalConversationBinding.ServiceStatus.ENDED)
    pairs = list(bindings.values_list("thread_id", "thread__member_id"))
    counts = unread_counts_by_thread(doctor=doctor, thread_ids=[thread_id for thread_id, _ in pairs])
    totals: dict[int, int] = {}
    for thread_id, member_id in pairs:
        totals[int(member_id)] = totals.get(int(member_id), 0) + counts.get(thread_id, 0)
    return totals


def mark_conversation_read(*, request, doctor: DoctorProfile, thread_id, last_read_message_id=None) -> dict:
    """消息成功加载后推进当前问诊已读游标（只前进不回退）。

    未显式给定消息 ID 时，以当前问诊最新一条可见消息为已读位置。
    """
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

    latest_id = (
        ChatMessage.objects.filter(thread_id=thread_id, tombstone=False).order_by("-id").values_list("id", flat=True).first()
    ) or 0
    if last_read_message_id is not None:
        try:
            candidate = int(last_read_message_id)
        except (TypeError, ValueError):
            raise HospitalCareError("PAYLOAD_INVALID", details={"field": "last_read_message_id"})
        if candidate < 0 or candidate > int(latest_id):
            raise HospitalCareError("PAYLOAD_INVALID", details={"field": "last_read_message_id"})
        target = candidate
    else:
        target = int(latest_id)

    with transaction.atomic():
        cursor, _ = DoctorConversationReadCursor.objects.select_for_update().get_or_create(
            doctor=doctor,
            thread_id=thread_id,
            defaults={"last_read_message_id": 0},
        )
        if target > int(cursor.last_read_message_id or 0):
            cursor.last_read_message_id = target
            cursor.save(update_fields=["last_read_message_id", "updated_at"])
    write_hospital_audit_log(
        request,
        action="hospital.conversation.read",
        resource_type="hospital_conversation",
        resource_id=str(thread_id),
        extra={
            "hospital_id": str(binding.hospital_id),
            "doctor_id": str(doctor.id),
            "thread_id": str(thread_id),
        },
    )
    remaining = unread_counts_by_thread(doctor=doctor, thread_ids=[thread_id]).get(thread_id, 0)
    return {
        "thread_id": str(thread_id),
        "last_read_message_id": int(cursor.last_read_message_id or 0),
        "unread_count": remaining,
    }


def conversation_activity_summaries(thread_ids: list) -> dict:
    """按问诊返回 {thread_id: {"excerpt": 患者首句, "doctor_replied": 医生是否已回复}}。"""
    if not thread_ids:
        return {}
    messages = (
        ChatMessage.objects.filter(
            thread_id__in=thread_ids,
            tombstone=False,
            hospital_attribution__actor_type__in=(
                ChatMessageAttribution.ActorType.PATIENT,
                ChatMessageAttribution.ActorType.DOCTOR,
            ),
        )
        .values("thread_id", "id", "hospital_attribution__actor_type")
        .order_by("thread_id", "id")
    )
    summaries: dict = {}
    doctor_replied: set = set()
    first_patient_id: dict = {}
    for row in messages:
        actor = row["hospital_attribution__actor_type"]
        if actor == ChatMessageAttribution.ActorType.DOCTOR:
            doctor_replied.add(row["thread_id"])
        elif row["thread_id"] not in first_patient_id:
            first_patient_id[row["thread_id"]] = row["id"]
    excerpts: dict = {}
    if first_patient_id:
        first_messages = (
            ChatMessage.objects.filter(id__in=first_patient_id.values())
            .prefetch_related("blocks")
        )
        for message in first_messages:
            excerpts[message.id] = _message_text_excerpt(message)
    for thread_id in thread_ids:
        first_id = first_patient_id.get(thread_id)
        summaries[thread_id] = {
            "excerpt": excerpts.get(first_id, "") if first_id else "",
            "doctor_replied": thread_id in doctor_replied,
        }
    return summaries


def _message_text_excerpt(message, limit: int = 80) -> str:
    pieces: list[str] = []
    for block in message.blocks.all():
        payload = block.payload or {}
        text = payload.get("text")
        if isinstance(text, dict):
            for key in sorted(text.keys()):
                value = text.get(key)
                if isinstance(value, str) and value.strip():
                    pieces.append(value.strip())
        elif isinstance(text, str) and text.strip():
            pieces.append(text.strip())
    return " ".join(pieces).strip()[:limit]


def attachment_count_for_threads(thread_ids: list) -> dict:
    """按问诊统计附件条数（imageGallery/fileGallery 块中的文件项总数）。"""
    if not thread_ids:
        return {}
    from chat_sync.models import ChatMessageBlock

    blocks = ChatMessageBlock.objects.filter(
        thread_id__in=thread_ids,
        kind__in=["imageGallery", "fileGallery", "fileAttachments"],
        message__tombstone=False,
    ).values("thread_id", "payload")
    counts = {thread_id: 0 for thread_id in thread_ids}
    for block in blocks:
        payload = block.get("payload") or {}
        items = 0
        for key in ("image_gallery", "file_gallery", "file_attachments"):
            gallery = payload.get(key)
            if isinstance(gallery, dict):
                for value in gallery.values():
                    if isinstance(value, list):
                        items += len(value)
        counts[block["thread_id"]] = counts.get(block["thread_id"], 0) + items
    return counts
