from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from accounts.models import SocialIdentity
from chat_sync.models import ChatThread
from hospital_care.exceptions import HospitalCareError
from hospital_care.models import (
    ChatMessageAttribution,
    ClinicalConversationBinding,
    DoctorPatientAttention,
    DoctorProfile,
)
from hospital_care.selectors.doctor_workspace import doctor_agent
from hospital_care.selectors.patient_workspace import (
    doctor_patient_conversations,
    doctor_patient_rows,
    get_visible_member,
)
from hospital_care.services.audit import write_hospital_audit_log
from hospital_care.services.conversation_service import _create_doctor_intro_card, _create_system_message
from hospital_care.services.read_state_service import unread_totals_by_member
from medical.models import Member, MemberMedicalProfile

_QUEUE_VALUES = {"all", "priority", "pending", "active", "ended"}


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


def _patient_phone(member: Member) -> str:
    """DOCTOR-WORKSPACE-000004 第 11 问：授权医生可查看完整手机号（界面不脱敏）。"""
    identity = (
        SocialIdentity.objects.filter(user_id=member.user_id, provider=SocialIdentity.Provider.PHONE)
        .order_by("-updated_at")
        .first()
    )
    if identity is None:
        return ""
    return (identity.provider_uid or "").strip()


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
    """D-007~D-010 + DOCTOR-WORKSPACE-000004：授权集合内搜索、筛选、排序。

    列表只包含至少存在一条授权问诊的患者；卡片附带未结束问诊未读总数；
    重点标记以医生-患者维度为准（兼容旧的问诊级聚合）。
    """
    rows = doctor_patient_rows(doctor=doctor)
    member_ids = [row["member_id"] for row in rows]
    members = {
        member.id: member
        for member in Member.all_objects.filter(id__in=member_ids, is_deleted=False)
    }
    rows = [row for row in rows if row["member_id"] in members]

    # 医生-患者级重点标记（第 23 问）：优先于问诊级聚合结果。
    attention_levels = {
        int(row.member_id): row.level
        for row in DoctorPatientAttention.objects.filter(doctor=doctor, member_id__in=member_ids)
    }
    for row in rows:
        level = attention_levels.get(row["member_id"])
        if level is not None:
            row["priority_patient"] = level == ClinicalConversationBinding.AttentionLevel.PRIORITY

    # 第 19 问：患者卡片未读 = 该患者所有未结束问诊的未读消息总数。
    unread_totals = unread_totals_by_member(doctor=doctor)

    counts = {
        "all": len(rows),
        "priority": sum(1 for row in rows if row["priority_patient"]),
        "pending": sum(
            1
            for row in rows
            if row["service_status"] == ClinicalConversationBinding.ServiceStatus.PENDING_DOCTOR
        ),
        "active": sum(
            1
            for row in rows
            if row["service_status"] == ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED
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
    elif queue == "active":
        rows = [
            row
            for row in rows
            if row["service_status"] == ClinicalConversationBinding.ServiceStatus.DOCTOR_JOINED
        ]
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
            "unread_count": int(unread_totals.get(row["member_id"], 0)),
        }
        for row in rows
    ]
    return items, counts


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
            # 第 11 问（范围修订）：授权医生界面不脱敏；phone_masked 保留给旧客户端兼容。
            "phone": _patient_phone(member) or None,
            "phone_masked": mask_phone(_patient_phone(member)) or None,
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
