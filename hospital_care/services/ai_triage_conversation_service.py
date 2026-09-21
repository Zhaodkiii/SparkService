from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone as django_timezone

from ai_config.models import AIScenarioModelBinding, ScenarioKey
from chat_sync.contracts.canonical import (
    KIND_AI_TRIAGE_GUIDE_CARD,
    KIND_HOSPITAL_TRIAGE_INTRO_CARD,
    ai_triage_guide_card_payload,
    hospital_triage_intro_card_payload,
)
from chat_sync.models import ChatMessage, ChatMessageBlock, ChatThread
from hospital_care.exceptions import HospitalCareError
from hospital_care.models import Hospital
from hospital_care.models.triage import HospitalAITriageBinding
from hospital_care.services.audit import write_hospital_audit_log
from medical.models import Member
from medical.services.member_binding_service import ensure_can_access_member


def _resolve_ai_triage_scenario_binding():
    binding = (
        AIScenarioModelBinding.objects.select_related("model")
        .filter(scenario=ScenarioKey.AI_TRIAGE, is_active=True, model__is_active=True)
        .order_by("-is_default", "position", "id")
        .first()
    )
    if binding is None:
        raise HospitalCareError("AI_TRIAGE_BINDING_MISSING")
    return binding


def _create_system_block_message(*, thread: ChatThread, kind: str, payload: dict, order_key: int) -> ChatMessage:
    now = django_timezone.now()
    message = ChatMessage.objects.create(
        user=thread.user,
        thread=thread,
        role=ChatMessage.Role.SYSTEM,
        client_message_id=uuid.uuid4(),
        server_message_id=str(uuid.uuid4()),
        delivery_state=ChatMessage.DeliveryState.SENT,
        created_at=now,
    )
    ChatMessageBlock.objects.create(
        id=uuid.uuid4(),
        user=thread.user,
        thread=thread,
        message=message,
        kind=kind,
        status=ChatMessageBlock.Status.READY,
        revision=1,
        order_key=order_key,
        node_role="timeline",
        payload=payload,
        created_at=now,
        updated_at=now,
    )
    return message


def _insert_triage_initial_messages(*, thread: ChatThread, hospital: Hospital, member_id: int) -> None:
    """AI 导诊保留医院介绍，但不投放科普问答和患者信息卡片。"""
    member = Member.objects.filter(pk=member_id).only("name").first()
    _create_system_block_message(
        thread=thread,
        kind=KIND_HOSPITAL_TRIAGE_INTRO_CARD,
        payload=hospital_triage_intro_card_payload(
            hospital_name=hospital.name,
            hospital_short_name=hospital.short_name or hospital.name,
            member_id=member_id,
            member_display_name=(member.name if member else "") or "患者",
            service_title="AI 导诊",
            introduction_excerpt=(hospital.introduction or "").strip()[:160],
        ),
        order_key=900,
    )
    _create_system_block_message(
        thread=thread,
        kind=KIND_AI_TRIAGE_GUIDE_CARD,
        payload=ai_triage_guide_card_payload(
            title="开始描述您的不适",
            subtitle="AI 将根据症状辅助推荐科室与就医建议，不能替代医生诊断。",
            disclaimer="急危重症或持续加重请立即线下就医或拨打 120。",
            prompts=[
                {"id": "headache", "title": "头痛、头晕", "message": "我最近头痛头晕，想咨询应该挂什么科？"},
                {"id": "chest", "title": "胸闷、心悸", "message": "我有胸闷心悸的感觉，请帮我看看建议去哪个科室？"},
                {"id": "stomach", "title": "腹痛、消化不适", "message": "我肚子不舒服，有点腹痛，请问可能挂什么科？"},
                {"id": "custom", "title": "其他症状", "message": "我想描述其他不适症状，请引导我继续说明。"},
            ],
        ),
        order_key=1000,
    )


def create_patient_ai_triage_conversation(
    *,
    request,
    user,
    hospital_id,
    member_id: int,
    thread_id=None,
) -> HospitalAITriageBinding:
    try:
        ensure_can_access_member(user=user, member_id=int(member_id))
    except PermissionError as exc:
        raise HospitalCareError("MEMBER_ACCESS_DENIED") from exc

    hospital = Hospital.objects.filter(pk=hospital_id, status=Hospital.Status.ACTIVE).first()
    if hospital is None:
        raise HospitalCareError("HOSPITAL_INACTIVE")

    scenario_binding = _resolve_ai_triage_scenario_binding()
    client_thread_id = thread_id or uuid.uuid4()
    existing_thread = ChatThread.objects.filter(user=user, id=client_thread_id).first()
    if existing_thread is not None:
        existing = HospitalAITriageBinding.objects.filter(thread=existing_thread).first()
        if existing is not None:
            if existing.hospital_id != hospital.id:
                raise HospitalCareError("CONVERSATION_REBIND_FORBIDDEN")
            return existing
        raise HospitalCareError("CONVERSATION_REBIND_FORBIDDEN")

    # 医院 Tab / 新建导诊：每次未指定 thread_id 都创建新会话，不复用历史导诊 Thread。
    with transaction.atomic():
        thread = ChatThread.objects.create(
            id=client_thread_id,
            user=user,
            member_id=int(member_id),
            title="AI 导诊",
            role_prompt=scenario_binding.system_provision or "",
        )
        binding = HospitalAITriageBinding.objects.create(
            thread=thread,
            hospital=hospital,
            scenario_binding=scenario_binding,
        )
        _insert_triage_initial_messages(thread=thread, hospital=hospital, member_id=int(member_id))

    write_hospital_audit_log(
        request,
        action="hospital.ai_triage.conversation.create",
        resource_type="hospital_ai_triage",
        resource_id=str(thread.id),
        extra={
            "hospital_id": str(hospital.id),
            "thread_id": str(thread.id),
            "member_id": int(member_id),
        },
    )
    return binding
