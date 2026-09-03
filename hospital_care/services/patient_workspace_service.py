from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from accounts.models import SocialIdentity
from chat_sync.models import ChatMessage, ChatThread
from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    ChatMessageAttribution,
    ClinicalConversationBinding,
    DoctorPatientSummary,
    DoctorPatientSummaryAck,
    DoctorProfile,
)
from hospital_care.selectors.doctor_workspace import doctor_agent
from hospital_care.selectors.patient_workspace import (
    assert_doctor_can_view_member,
    doctor_patient_conversations,
    doctor_patient_rows,
    get_visible_member,
)
from hospital_care.services.audit import write_hospital_audit_log
from hospital_care.services.conversation_service import _create_doctor_intro_card, _create_system_message
from medical.models import Member, MemberMedicalProfile

SUMMARY_TOOL_NAME = "patient-workspace-summary-v1"

_QUEUE_VALUES = {"all", "priority", "pending", "ended"}

_RISK_ORDER = {
    ClinicalConversationBinding.RiskSignalLevel.NONE: 0,
    ClinicalConversationBinding.RiskSignalLevel.LOW: 1,
    ClinicalConversationBinding.RiskSignalLevel.MEDIUM: 2,
    ClinicalConversationBinding.RiskSignalLevel.HIGH: 3,
}

_RISK_SUGGESTION = {
    ClinicalConversationBinding.RiskSignalLevel.LOW: "按现有风险工具建议继续观察。",
    ClinicalConversationBinding.RiskSignalLevel.MEDIUM: "按现有风险工具建议尽快人工跟进；人工调整请进入现有风险工具流程。",
    ClinicalConversationBinding.RiskSignalLevel.HIGH: "按现有风险工具建议立即人工介入处理；人工调整请进入现有风险工具流程。",
}


def mask_phone(value: str) -> str:
    """服务端脱敏：完整手机号不下发。无法识别时返回空串（前端显示“未填写”）。"""
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    if len(digits) >= 7:
        return f"{digits[:3]}****{digits[-4:]}"
    return ""


def patient_number_for(member: Member) -> str:
    """派生患者编号：当前无独立患者编号字段，使用 member_id 生成稳定展示编号。"""
    return f"P{int(member.id):010d}"


def masked_patient_identifier(member: Member) -> str:
    """D-008：列表卡片脱敏标识，保留前缀与末四位。"""
    number = patient_number_for(member)
    if len(number) <= 8:
        return number
    return f"{number[:5]}****{number[-4:]}"


def _member_age(member: Member) -> int | None:
    birth = getattr(member, "birth_date", None)
    if not birth:
        return None
    today = timezone.localdate()
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return max(years, 0)


def _extra_value(extra: dict | None, *keys: str) -> str:
    if not extra:
        return ""
    for key in keys:
        value = (extra.get(key) or "").strip() if isinstance(extra.get(key), str) else ""
        if value:
            return value
        raw = extra.get(key)
        if raw is not None and not isinstance(raw, (dict, list)):
            text = str(raw).strip()
            if text:
                return text
    return ""


def _parse_float(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _patient_phone_masked(member: Member) -> str:
    identity = (
        SocialIdentity.objects.filter(user_id=member.user_id, provider=SocialIdentity.Provider.PHONE)
        .order_by("-updated_at")
        .first()
    )
    if identity is None:
        return ""
    return mask_phone(identity.provider_uid)


def _profile_for(member: Member) -> MemberMedicalProfile | None:
    return (
        MemberMedicalProfile.all_objects.filter(member_id=member.id, user_id=member.user_id, is_deleted=False)
        .order_by("-updated_at", "-id")
        .first()
    )


def build_health_profile(member: Member, profile: MemberMedicalProfile | None) -> dict:
    """D-004 健康档案分区：缺失字段返回 None，客户端显示“未填写”。"""
    extra = dict(profile.extra or {}) if profile is not None else {}
    height = _parse_float(_extra_value(extra, "height_cm"))
    weight = _parse_float(_extra_value(extra, "weight_kg"))
    bmi = None
    if height and weight and height > 0:
        bmi = round(weight / ((height / 100) ** 2), 1)
    smoking = (profile.smoking_profile or {}) if profile is not None else {}
    drinking = (profile.drinking_profile or {}) if profile is not None else {}
    return {
        "height_cm": height,
        "weight_kg": weight,
        "bmi": bmi,
        "blood_type": (member.blood_type or "").strip() or None,
        "smoking_status": (smoking.get("status") or "").strip() or None,
        "drinking_status": (drinking.get("status") or "").strip() or None,
    }


def build_medical_safety(member: Member, profile: MemberMedicalProfile | None) -> dict:
    """D-004 医疗安全信息分区：空数组表示“已查询但无记录”。"""
    allergies: list[str] = []
    if profile is not None and profile.allergies:
        allergies = [str(item) for item in profile.allergies if str(item).strip()]
    elif member.allergies:
        allergies = [str(item) for item in member.allergies if str(item).strip()]

    medications: list[str] = []
    if profile is not None:
        for item in profile.medication_focus or []:
            name = (item.get("drug_name") or "").strip() if isinstance(item, dict) else ""
            if name:
                summary = (item.get("summary") or "").strip()
                medications.append(f"{name} · {summary}" if summary else name)

    past_history: list[str] = []
    if profile is not None and profile.chronic_conditions:
        past_history = [str(item) for item in profile.chronic_conditions if str(item).strip()]
    elif member.chronic_conditions:
        past_history = [str(item) for item in member.chronic_conditions if str(item).strip()]

    return {
        "allergies": allergies,
        "long_term_medications": medications,
        "past_medical_history": past_history,
    }


def build_patient_list(*, doctor: DoctorProfile, keyword: str = "", queue: str = "all") -> tuple[list[dict], dict[str, int]]:
    """D-007~D-010：授权集合内搜索、筛选、排序，返回最小卡片摘要与计数。"""
    rows = doctor_patient_rows(doctor=doctor)
    member_ids = [row["member_id"] for row in rows]
    members = {
        member.id: member
        for member in Member.all_objects.filter(id__in=member_ids, is_deleted=False)
    }
    rows = [row for row in rows if row["member_id"] in members]

    counts = {
        "all": len(rows),
        "priority": sum(1 for row in rows if row["priority_patient"]),
        "pending": sum(
            1
            for row in rows
            if row["service_status"] == ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR
        ),
        "ended": sum(
            1 for row in rows if row["service_status"] == ClinicalConversationBinding.ServiceStatus.ENDED
        ),
    }

    if queue not in _QUEUE_VALUES:
        queue = "all"
    if queue == "priority":
        rows = [row for row in rows if row["priority_patient"]]
    elif queue == "pending":
        rows = [
            row
            for row in rows
            if row["service_status"] == ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR
        ]
    elif queue == "ended":
        rows = [row for row in rows if row["service_status"] == ClinicalConversationBinding.ServiceStatus.ENDED]

    keyword = (keyword or "").strip().lower()
    if keyword:
        def _matches(row: dict) -> bool:
            member = members[row["member_id"]]
            name = (member.name or "").strip().lower()
            identifier = masked_patient_identifier(member).lower()
            return keyword in name or keyword in identifier

        rows = [row for row in rows if _matches(row)]

    # D-009：重点患者优先；最近会话时间倒序（无会话时间排后）；member_id 稳定键。
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
        }
        for row in rows
    ]
    return items, counts


def build_risk_card(*, doctor: DoctorProfile, member_id: int) -> dict | None:
    """D-024~D-026：风险卡片只读聚合现有风险信号；不提供人工调整。

    取当前医生可见会话中等级最高（平级取最新）的风险信号。
    """
    bindings = doctor_patient_conversations(doctor=doctor, member_id=member_id)
    best: ClinicalConversationBinding | None = None
    for binding in bindings:
        level = binding.risk_signal_level or ClinicalConversationBinding.RiskSignalLevel.NONE
        if level == ClinicalConversationBinding.RiskSignalLevel.NONE:
            continue
        if best is None:
            best = binding
            continue
        best_level = best.risk_signal_level or ClinicalConversationBinding.RiskSignalLevel.NONE
        if (_RISK_ORDER.get(level, 0), binding.updated_at) > (_RISK_ORDER.get(best_level, 0), best.updated_at):
            best = binding
    if best is None:
        return None
    level = best.risk_signal_level
    return {
        "level": level,
        "status": "effective",
        "suggestion": _RISK_SUGGESTION.get(level, "按现有风险工具建议处理。"),
        "source_thread_id": str(best.thread_id),
        "updated_at": best.updated_at.isoformat(),
        "data_cutoff_at": best.updated_at.isoformat(),
        "source": "existing_risk_tool",
    }


def _extract_message_text(message: ChatMessage) -> str:
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
    return " ".join(pieces).strip()


def _recent_patient_messages(*, doctor: DoctorProfile, member_id: int, limit: int = 3) -> list[str]:
    bindings = doctor_patient_conversations(doctor=doctor, member_id=member_id)
    thread_ids = [binding.thread_id for binding in bindings]
    if not thread_ids:
        return []
    messages = (
        ChatMessage.objects.filter(
            thread_id__in=thread_ids,
            tombstone=False,
            hospital_attribution__actor_type=ChatMessageAttribution.ActorType.PATIENT,
        )
        .prefetch_related("blocks")
        .order_by("-created_at", "-id")[: limit * 3]
    )
    texts: list[str] = []
    for message in messages:
        text = _extract_message_text(message)
        if text:
            texts.append(text[:80])
        if len(texts) >= limit:
            break
    return texts


def generate_patient_summary(*, request, doctor: DoctorProfile, member_id: int) -> DoctorPatientSummary:
    """D-020~D-023：医生主动触发生成；输入范围 = 当前医生可见资料 + 可见会话。

    生成内容为系统结构化摘要（确定性生成，可追溯到输入快照），
    不回写 Member、健康档案、会话或风险等级。
    """
    member = get_visible_member(doctor=doctor, member_id=member_id)
    profile = _profile_for(member)
    bindings = list(doctor_patient_conversations(doctor=doctor, member_id=member_id))

    latest = bindings[0] if bindings else None
    status_label = {
        ClinicalConversationBinding.ServiceStatus.AI_ACTIVE: "AI 服务中",
        ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR: "待医生接管",
        ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED: "医生已接管",
        ClinicalConversationBinding.ServiceStatus.ENDED: "已结束",
    }
    if latest is not None:
        current_issues = (
            f"最近咨询「{latest.thread.title or latest.agent.name}」，"
            f"当前服务状态：{status_label.get(latest.service_status, '状态未知')}；"
            f"当前医生可见会话共 {len(bindings)} 条。"
        )
    else:
        current_issues = "暂无可查看的院内会话。"

    safety = build_medical_safety(member, profile)
    health = build_health_profile(member, profile)
    health_pieces: list[str] = []
    if health["blood_type"]:
        health_pieces.append(f"血型 {health['blood_type']}")
    if health["bmi"] is not None:
        health_pieces.append(f"BMI {health['bmi']}")
    if safety["allergies"]:
        health_pieces.append(f"过敏：{'、'.join(safety['allergies'][:5])}")
    if safety["long_term_medications"]:
        health_pieces.append(f"长期用药：{'、'.join(safety['long_term_medications'][:5])}")
    if safety["past_medical_history"]:
        health_pieces.append(f"既往病史：{'、'.join(safety['past_medical_history'][:5])}")
    key_health_info = "；".join(health_pieces) if health_pieces else "暂无已记录的关键健康信息。"

    patient_messages = _recent_patient_messages(doctor=doctor, member_id=member_id)
    if patient_messages:
        conversation_highlights = "；".join(f"患者：{text}" for text in patient_messages)
    elif latest is not None:
        conversation_highlights = f"最近会话「{latest.thread.title or latest.agent.name}」暂无患者正文消息。"
    else:
        conversation_highlights = "暂无会话要点。"

    follow_ups: list[str] = []
    for binding in bindings:
        if binding.service_status == ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR:
            follow_ups.append("存在待接管会话，请及时处理。")
            break
    for binding in bindings:
        if (
            binding.doctor_attention_level == ClinicalConversationBinding.AttentionLevel.PRIORITY
            and binding.service_status != ClinicalConversationBinding.ServiceStatus.ENDED
        ):
            follow_ups.append("重点患者标记生效中，请优先跟进。")
            break
    risk_card = build_risk_card(doctor=doctor, member_id=member_id)
    if risk_card is not None:
        follow_ups.append(f"引用风险评估结果：{risk_card['level']} 风险信号，请在现有风险工具流程中处理。")

    now = timezone.now()
    input_snapshot = {
        "hospital_id": str(doctor.staff_membership.hospital_id),
        "doctor_id": str(doctor.id),
        "member_id": int(member.id),
        "thread_ids": [str(binding.thread_id) for binding in bindings],
        "profile_updated_at": profile.updated_at.isoformat() if profile is not None else None,
        "conversation_cutoff_at": latest.updated_at.isoformat() if latest is not None else None,
        "tool_name": SUMMARY_TOOL_NAME,
        "generated_at": now.isoformat(),
    }

    with transaction.atomic():
        latest_version = (
            DoctorPatientSummary.objects.filter(doctor=doctor, member_id=member.id)
            .order_by("-version")
            .values_list("version", flat=True)
            .first()
        ) or 0
        summary = DoctorPatientSummary.objects.create(
            hospital_id=doctor.staff_membership.hospital_id,
            doctor=doctor,
            member_id=member.id,
            version=latest_version + 1,
            status=DoctorPatientSummary.Status.READY,
            current_issues=current_issues,
            key_health_info=key_health_info,
            conversation_highlights=conversation_highlights,
            follow_up_items=follow_ups,
            input_snapshot=input_snapshot,
            tool_name=SUMMARY_TOOL_NAME,
        )
    write_hospital_audit_log(
        request,
        action="hospital.patient_summary.generate",
        resource_type="hospital_patient_summary",
        resource_id=str(summary.id),
        extra={
            "hospital_id": str(doctor.staff_membership.hospital_id),
            "doctor_id": str(doctor.id),
            "member_id": int(member.id),
            "version": summary.version,
        },
    )
    return summary


def get_latest_summary(*, doctor: DoctorProfile, member_id: int) -> DoctorPatientSummary | None:
    assert_doctor_can_view_member(doctor=doctor, member_id=member_id)
    return (
        DoctorPatientSummary.objects.filter(doctor=doctor, member_id=int(member_id))
        .order_by("-version")
        .first()
    )


def present_summary(summary: DoctorPatientSummary | None, *, doctor: DoctorProfile) -> dict | None:
    if summary is None:
        return None
    ack = DoctorPatientSummaryAck.objects.filter(summary=summary, doctor=doctor).first()
    snapshot = summary.input_snapshot or {}
    return {
        "id": str(summary.id),
        "version": summary.version,
        "status": summary.status,
        "system_generated": True,
        "sections": {
            "current_issues": summary.current_issues,
            "key_health_info": summary.key_health_info,
            "conversation_highlights": summary.conversation_highlights,
            "follow_up_items": list(summary.follow_up_items or []),
        },
        "data_scope": {
            "thread_count": len(snapshot.get("thread_ids") or []),
            "profile_updated_at": snapshot.get("profile_updated_at"),
            "conversation_cutoff_at": snapshot.get("conversation_cutoff_at"),
        },
        "tool_name": summary.tool_name,
        "generated_at": summary.generated_at.isoformat(),
        "acknowledged": bool(ack and ack.acknowledged),
        "acknowledged_at": ack.acted_at.isoformat() if ack and ack.acknowledged else None,
    }


def ack_summary(*, request, doctor: DoctorProfile, member_id: int, acknowledged: bool) -> dict:
    summary = get_latest_summary(doctor=doctor, member_id=member_id)
    if summary is None:
        raise HospitalCareError("SUMMARY_UNAVAILABLE")
    ack, _ = DoctorPatientSummaryAck.objects.update_or_create(
        summary=summary,
        doctor=doctor,
        defaults={"acknowledged": acknowledged},
    )
    write_hospital_audit_log(
        request,
        action="hospital.patient_summary.ack" if acknowledged else "hospital.patient_summary.unack",
        resource_type="hospital_patient_summary",
        resource_id=str(summary.id),
        extra={
            "hospital_id": str(doctor.staff_membership.hospital_id),
            "doctor_id": str(doctor.id),
            "member_id": int(member_id),
            "version": summary.version,
            "acknowledged": acknowledged,
        },
    )
    return present_summary(summary, doctor=doctor)


def build_patient_workspace(*, doctor: DoctorProfile, member_id: int) -> dict:
    """D-004/D-006/D-012：患者工作台只读聚合快照。"""
    member = get_visible_member(doctor=doctor, member_id=member_id)
    profile = _profile_for(member)
    bindings = list(doctor_patient_conversations(doctor=doctor, member_id=member_id))
    latest = bindings[0] if bindings else None
    priority = any(
        binding.doctor_attention_level == ClinicalConversationBinding.AttentionLevel.PRIORITY
        and binding.service_status != ClinicalConversationBinding.ServiceStatus.ENDED
        for binding in bindings
    )
    extra = dict(profile.extra or {}) if profile is not None else {}
    return {
        "patient": {
            "member_id": member.id,
            "display_name": (member.name or "").strip() or "未命名患者",
            "gender": member.gender,
            "birth_date": member.birth_date.isoformat() if member.birth_date else None,
            "age": _member_age(member),
            "patient_number": patient_number_for(member),
            "avatar_url": member.avatar_url or "",
            "service_status": latest.service_status if latest is not None else None,
            "priority_patient": priority,
        },
        "basic_profile": {
            "phone_masked": _patient_phone_masked(member) or None,
            "identity_number_masked": _extra_value(extra, "identity_number_masked", "id_number_masked") or None,
            "region": _extra_value(extra, "region", "region_display") or None,
            "occupation": _extra_value(extra, "occupation") or None,
            "marital_status": _extra_value(extra, "marital_status") or None,
        },
        "health_profile": build_health_profile(member, profile),
        "medical_safety": build_medical_safety(member, profile),
        "work_flags": {"priority_patient": priority},
        "freshness": {
            "member_updated_at": member.updated_at.isoformat() if member.updated_at else None,
            "health_profile_updated_at": profile.updated_at.isoformat() if profile is not None else None,
            "snapshot_at": timezone.now().isoformat(),
        },
    }


def create_doctor_patient_conversation(*, request, doctor: DoctorProfile, member_id: int) -> ClinicalConversationBinding:
    """D-019：患者工作台新建咨询，自动继承当前患者与当前医生智能体上下文。

    服务端重新校验医生对患者的服务关系与智能体可用状态；始终创建新 Thread。
    """
    member = get_visible_member(doctor=doctor, member_id=member_id)
    agent = doctor_agent(doctor=doctor)
    if agent is None:
        raise HospitalCareError("AGENT_NOT_FOUND")
    if agent.publication_status != agent.PublicationStatus.PUBLISHED:
        raise HospitalCareError("AGENT_NOT_PUBLISHED")
    if agent.hospital_id != doctor.staff_membership.hospital_id:
        raise HospitalCareError("AGENT_DOCTOR_INVALID")

    now = timezone.now()
    with transaction.atomic():
        thread = ChatThread.objects.create(
            user=member.user,
            member_id=member.id,
            title=agent.name,
            role_prompt=agent.service_boundary,
        )
        binding = ClinicalConversationBinding.objects.create(
            thread=thread,
            hospital_id=doctor.staff_membership.hospital_id,
            department=agent.department,
            doctor=doctor,
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
            "hospital_id": str(doctor.staff_membership.hospital_id),
            "agent_id": str(agent.id),
            "thread_id": str(thread.id),
            "member_id": int(member.id),
            "initiated_by": "doctor_workspace",
        },
    )
    return binding
