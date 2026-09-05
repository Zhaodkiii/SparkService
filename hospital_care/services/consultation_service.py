"""线上问诊单服务（DOCTOR-WORKSPACE-000004 页面形态修订）。

- 患者客户端独立提交线上问诊：创建独立问诊单（Consultation），
  关联复用的 ChatThread / ClinicalConversationBinding 消息与状态机体系。
- 只有提交过线上问诊的患者才进入医生“线上问诊”工作台列表；
  患者工作台（DOCTOR-WORKSPACE-000001）口径不变，不读取问诊单。
"""

from __future__ import annotations

import uuid

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from chat_sync.models import ChatMessage, ChatMessageBlock
from file_manager.url_utils import managed_file_download_url
from medical.models import Member

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    ChatMessageAttribution,
    ClinicalConversationBinding,
    Consultation,
    DoctorPatientAttention,
    DoctorProfile,
)
from hospital_care.services.audit import write_hospital_audit_log
from hospital_care.services.conversation_service import create_patient_conversation
from hospital_care.services.doctor_message_service import resolve_message_attachments
from hospital_care.services.patient_workspace_service import masked_patient_identifier, patient_number_for
from hospital_care.services.read_state_service import (
    attachment_count_for_threads,
    conversation_activity_summaries,
    unread_counts_by_thread,
)

_CONSULT_QUEUE_VALUES = {"all", "priority", "pending", "active", "ended"}


def _next_consult_no(now) -> tuple[str, object, int]:
    """生成当日问诊编号：C + YYYYMMDD + 4 位当日序列。"""
    consult_date = now.date()
    last = (
        Consultation.objects.select_for_update()
        .filter(consult_date=consult_date)
        .aggregate(max_seq=Max("daily_seq"))
    )
    daily_seq = int(last["max_seq"] or 0) + 1
    return f"C{consult_date:%Y%m%d}{daily_seq:04d}", consult_date, daily_seq


def _create_first_patient_message(
    *,
    consultation_binding: ClinicalConversationBinding,
    user,
    member: Member | None,
    chief_complaint: str,
    attachments,
) -> ChatMessage:
    """问诊提交时的首条患者消息：主诉文本 + 可选附件画廊块。"""
    thread = consultation_binding.thread
    images, documents = resolve_message_attachments(user=user, attachments=attachments) if attachments else ([], [])
    now = timezone.now()
    metadata = {"hospital_actor": "patient"}
    if images or documents:
        metadata["attachments"] = [
            {
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
        role=ChatMessage.Role.USER,
        client_message_id=uuid.uuid4(),
        server_message_id=str(uuid.uuid4()),
        delivery_state=ChatMessage.DeliveryState.SENT,
        created_at=now,
        metadata=metadata,
    )
    if chief_complaint:
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
            payload={"text": {"_0": chief_complaint}},
            created_at=now,
            updated_at=now,
        )
    if images:
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
    ChatMessageAttribution.objects.create(
        message=message,
        actor_type=ChatMessageAttribution.ActorType.PATIENT,
        actor_user=user,
        display_name_snapshot=(member.name if member else "") or "患者",
        source=ChatMessageAttribution.Source.PATIENT_APP,
    )
    return message


def submit_consultation(
    *,
    request,
    user,
    agent_id,
    member_id: int,
    chief_complaint: str,
    attachments=None,
    order_items=None,
    past_history: str = "",
    family_history: str = "",
    allergy_history: str = "",
    thread_id=None,
) -> Consultation:
    """患者客户端提交线上问诊：创建会话绑定 + 首条主诉消息 + 独立问诊单。

    幂等：thread_id 已存在且已生成问诊单时直接返回原问诊单；
    外层由 run_idempotent_command 保证命令级幂等。
    """
    complaint = (chief_complaint or "").strip()
    if not complaint and not attachments:
        raise HospitalCareError("PAYLOAD_INVALID", details={"field": "chief_complaint"})

    existing_thread = None
    if thread_id is not None:
        from chat_sync.models import ChatThread

        existing_thread = ChatThread.objects.filter(user=user, id=thread_id).first()
        if existing_thread is not None:
            existing = Consultation.objects.filter(binding__thread=existing_thread).first()
            if existing is not None:
                return existing

    member = Member.all_objects.filter(pk=int(member_id), is_deleted=False).first()
    now = timezone.now()
    for _attempt in range(3):
        try:
            with transaction.atomic():
                binding = create_patient_conversation(
                    request=request,
                    user=user,
                    agent_id=agent_id,
                    member_id=int(member_id),
                    thread_id=thread_id,
                    flow="consultation",
                )
                # 幂等重放：binding 已存在时不再重复写入首条消息与问诊单。
                existing = Consultation.objects.filter(binding=binding).first()
                if existing is not None:
                    return existing
                _create_first_patient_message(
                    consultation_binding=binding,
                    user=user,
                    member=member,
                    chief_complaint=complaint,
                    attachments=attachments,
                )
                consult_no, consult_date, daily_seq = _next_consult_no(now)
                consultation = Consultation.objects.create(
                    binding=binding,
                    consult_no=consult_no,
                    consult_date=consult_date,
                    daily_seq=daily_seq,
                    member_id=int(member_id),
                    chief_complaint=complaint,
                    order_items=[str(item).strip() for item in (order_items or []) if str(item).strip()][:8],
                    past_history=(past_history or "").strip(),
                    family_history=(family_history or "").strip(),
                    allergy_history=(allergy_history or "").strip(),
                    submitted_by=user,
                )
            break
        except IntegrityError:
            # 当日序列并发冲突：重试取下一序列号。
            continue
    else:  # pragma: no cover - 并发极端兜底
        raise HospitalCareError("CONSULTATION_SUBMIT_FAILED")

    write_hospital_audit_log(
        request,
        action="hospital.consultation.submit",
        resource_type="hospital_consultation",
        resource_id=str(consultation.id),
        extra={
            "hospital_id": str(binding.hospital_id),
            "thread_id": str(binding.thread_id),
            "member_id": int(member_id),
            "consult_no": consultation.consult_no,
        },
    )
    return consultation


def _doctor_consultation_rows(*, doctor: DoctorProfile) -> list[dict]:
    """按患者聚合当前医生的线上问诊单（口径独立于患者工作台）。"""
    consultations = (
        Consultation.objects.filter(
            binding__doctor=doctor,
            binding__hospital_id=doctor.staff_membership.hospital_id,
            binding__thread__is_deleted=False,
        )
        .order_by("-submitted_at", "-id")
        .values(
            "member_id",
            "binding__service_status",
            "binding__doctor_attention_level",
            "binding__updated_at",
            "submitted_at",
        )
    )
    rows: dict[int, dict] = {}
    for item in consultations:
        member_id = int(item["member_id"])
        row = rows.get(member_id)
        if row is None:
            row = {
                "member_id": member_id,
                "service_status": item["binding__service_status"],
                "priority_patient": False,
                "latest_conversation_at": item["binding__updated_at"] or item["submitted_at"],
                "conversation_count": 0,
            }
            rows[member_id] = row
        row["conversation_count"] += 1
        if (
            item["binding__doctor_attention_level"] == ClinicalConversationBinding.AttentionLevel.PRIORITY
            and item["binding__service_status"] != ClinicalConversationBinding.ServiceStatus.ENDED
        ):
            row["priority_patient"] = True
        latest = item["binding__updated_at"] or item["submitted_at"]
        if latest and (row["latest_conversation_at"] is None or latest > row["latest_conversation_at"]):
            row["latest_conversation_at"] = latest
    return list(rows.values())


def _consult_unread_totals(*, doctor: DoctorProfile) -> dict[int, int]:
    """患者卡片未读 = 该患者未结束问诊单对应消息的未读总数。"""
    consultations = (
        Consultation.objects.filter(
            binding__doctor=doctor,
            binding__hospital_id=doctor.staff_membership.hospital_id,
            binding__thread__is_deleted=False,
        )
        .exclude(binding__service_status=ClinicalConversationBinding.ServiceStatus.ENDED)
        .values_list("member_id", "binding__thread_id")
    )
    thread_ids = [thread_id for _member_id, thread_id in consultations]
    unread_map = unread_counts_by_thread(doctor=doctor, thread_ids=thread_ids)
    totals: dict[int, int] = {}
    for member_id, thread_id in consultations:
        totals[int(member_id)] = totals.get(int(member_id), 0) + int(unread_map.get(thread_id, 0))
    return totals


def build_consult_patient_list(*, doctor: DoctorProfile, keyword: str = "", queue: str = "all") -> tuple[list[dict], dict[str, int]]:
    """线上问诊患者列表：仅包含提交过线上问诊的患者。

    输出结构与患者工作台患者列表一致（items + counts），但数据源仅为问诊单。
    """
    rows = _doctor_consultation_rows(doctor=doctor)
    member_ids = [row["member_id"] for row in rows]
    members = {member.id: member for member in Member.all_objects.filter(id__in=member_ids, is_deleted=False)}
    rows = [row for row in rows if row["member_id"] in members]

    attention_levels = {
        int(row.member_id): row.level
        for row in DoctorPatientAttention.objects.filter(doctor=doctor, member_id__in=member_ids)
    }
    for row in rows:
        level = attention_levels.get(row["member_id"])
        if level is not None:
            row["priority_patient"] = level == ClinicalConversationBinding.AttentionLevel.PRIORITY

    unread_totals = _consult_unread_totals(doctor=doctor)

    counts = {
        "all": len(rows),
        "priority": sum(1 for row in rows if row["priority_patient"]),
        "pending": sum(
            1 for row in rows if row["service_status"] == ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR
        ),
        "active": sum(
            1 for row in rows if row["service_status"] == ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED
        ),
        "ended": sum(1 for row in rows if row["service_status"] == ClinicalConversationBinding.ServiceStatus.ENDED),
    }

    if queue not in _CONSULT_QUEUE_VALUES:
        queue = "all"
    if queue == "priority":
        rows = [row for row in rows if row["priority_patient"]]
    elif queue == "pending":
        rows = [row for row in rows if row["service_status"] == ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR]
    elif queue == "active":
        rows = [row for row in rows if row["service_status"] == ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED]
    elif queue == "ended":
        rows = [row for row in rows if row["service_status"] == ClinicalConversationBinding.ServiceStatus.ENDED]

    keyword = (keyword or "").strip().lower()
    if keyword:

        def _matches(row: dict) -> bool:
            member = members[row["member_id"]]
            name = (member.name or "").strip().lower()
            identifier = masked_patient_identifier(member).lower()
            full_number = patient_number_for(member).lower()
            return keyword in name or keyword in identifier or keyword in full_number

        rows = [row for row in rows if _matches(row)]

    rows.sort(
        key=lambda row: (
            0 if row["priority_patient"] else 1,
            0 if row["latest_conversation_at"] is not None else 1,
            -(row["latest_conversation_at"].timestamp() if row["latest_conversation_at"] else 0),
            row["member_id"],
        )
    )

    items = [
        {
            "member_id": row["member_id"],
            "display_name": (members[row["member_id"]].name or "").strip() or "未命名患者",
            "masked_patient_identifier": masked_patient_identifier(members[row["member_id"]]),
            "service_status": row["service_status"],
            "latest_conversation_at": row["latest_conversation_at"].isoformat() if row["latest_conversation_at"] else None,
            "priority_patient": row["priority_patient"],
            "available_conversation_count": row["conversation_count"],
            "unread_count": int(unread_totals.get(row["member_id"], 0)),
        }
        for row in rows
    ]
    return items, counts


def doctor_member_consultations(*, doctor: DoctorProfile, member_id: int) -> list[Consultation]:
    """当前医生对该患者可见的全部线上问诊单，按提交时间倒序。"""
    return list(
        Consultation.objects.select_related(
            "binding",
            "binding__thread",
            "binding__hospital",
            "binding__department",
            "binding__doctor",
            "binding__agent",
        )
        .filter(
            binding__doctor=doctor,
            binding__hospital_id=doctor.staff_membership.hospital_id,
            binding__thread__is_deleted=False,
            member_id=int(member_id),
        )
        .order_by("-submitted_at", "-id")
    )
