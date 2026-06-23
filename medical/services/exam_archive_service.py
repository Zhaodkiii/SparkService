"""体检档案 AI 计划闭环：异常项提取、随访草稿、体检计划生成与画像投影。"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from medical.models import (
    HealthExamReport,
    MedExamDetail,
    Member,
    MemberMedicalExamPlan,
    MemberMedicalKeyIndicatorRecord,
    MemberMedicalProfile,
    Symptom,
)
from medical.services.member_medical_profile_service import build_member_medical_guidance_projection
from task_system.models import (
    Task,
    TaskMedical,
    TaskNotification,
    TaskNotificationStatus,
    TaskPriority,
    TaskSource,
    TaskStatus,
    TaskType,
)

logger = logging.getLogger(__name__)

DEFAULT_RISK_NOTICE = (
    "本建议仅用于健康管理和体检规划，不替代医生诊断。"
    "如有明显不适、症状加重或急症风险，请及时就医。"
)

ABNORMAL_FLAGS = {"h", "l", "high", "low", "abnormal", "阳性", "↑", "↓", "偏高", "偏低", "异常"}

BASELINE_MUST_ITEMS = [
    {"key": "cbc", "name": "血常规"},
    {"key": "urine", "name": "尿常规"},
    {"key": "liver_function", "name": "肝功能"},
    {"key": "kidney_function", "name": "肾功能"},
    {"key": "blood_lipid", "name": "血脂四项"},
    {"key": "fasting_glucose", "name": "空腹血糖"},
]

FOLLOW_UP_RULES: list[dict[str, Any]] = [
    {
        "pattern": r"甲状腺|tsh|t3|t4|ti-rads",
        "key": "thyroid_ultrasound_3m",
        "title": "3个月内复查甲状腺彩超",
        "medical_task_type": "thyroid_ultrasound_follow_up",
        "due_in_days": 90,
        "priority": "medium",
    },
    {
        "pattern": r"ldl|血脂|胆固醇|甘油三酯|hdl",
        "key": "blood_lipid_3m",
        "title": "3个月内复查血脂四项",
        "medical_task_type": "blood_lipid_follow_up",
        "due_in_days": 90,
        "priority": "medium",
    },
    {
        "pattern": r"肝|脂肪肝|alt|ast|ggt",
        "key": "liver_function_6m",
        "title": "6个月内复查肝功能",
        "medical_task_type": "liver_function_follow_up",
        "due_in_days": 180,
        "priority": "low",
    },
    {
        "pattern": r"肾|肌酐|尿素|尿酸",
        "key": "kidney_function_6m",
        "title": "6个月内复查肾功能",
        "medical_task_type": "kidney_function_follow_up",
        "due_in_days": 180,
        "priority": "medium",
    },
    {
        "pattern": r"血糖|糖化|hba1c|糖尿病",
        "key": "glucose_3m",
        "title": "3个月内复查空腹血糖",
        "medical_task_type": "glucose_follow_up",
        "due_in_days": 90,
        "priority": "medium",
    },
]


def _slug_key(text: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "_", (text or "").strip().lower())
    normalized = normalized.strip("_")
    if normalized:
        return normalized[:48]
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def _is_abnormal_detail(detail: MedExamDetail) -> bool:
    flag = (detail.flag or "").strip().lower()
    if flag and any(token in flag for token in ABNORMAL_FLAGS):
        return True
    diagnosis = (detail.diagnosis or "").strip()
    if diagnosis and any(token in diagnosis for token in ("异常", "偏高", "偏低", "结节", "囊肿", "增生")):
        return True
    return False


def _severity_from_flag(flag: str) -> str:
    lowered = (flag or "").lower()
    if any(token in lowered for token in ("h", "high", "↑", "偏高", "阳性")):
        return "medium"
    if any(token in lowered for token in ("l", "low", "↓", "偏低")):
        return "low"
    return "medium"


def extract_abnormal_items_from_report(*, report: HealthExamReport) -> list[dict[str, Any]]:
    details = MedExamDetail.objects.filter(
        is_deleted=False,
        business_type=MedExamDetail.BusinessType.HEALTH_EXAM_REPORT,
        business_id=report.id,
        member_id=report.member_id,
    ).order_by("sort_order", "id")

    items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for detail in details:
        if not _is_abnormal_detail(detail):
            continue
        name = (detail.item_name or detail.sub_category or detail.category or "异常指标").strip()
        key = _slug_key(name)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        suggestion = (detail.diagnosis or "").strip()
        if not suggestion and detail.reference_range:
            suggestion = f"参考范围 {detail.reference_range}"
        items.append(
            {
                "key": key,
                "code": key,
                "name": name,
                "value": (detail.result_value or "").strip(),
                "unit": (detail.unit or "").strip(),
                "severity": _severity_from_flag(detail.flag),
                "reason": suggestion or "报告标记为异常",
                "suggestion": suggestion,
            }
        )

    summary = (report.summary or "").strip()
    if summary and not items:
        for chunk in re.split(r"[;；、,\n]", summary):
            text = chunk.strip()
            if not text or len(text) < 2:
                continue
            if not any(token in text for token in ("异常", "偏高", "偏低", "结节", "囊肿", "脂肪肝", "增高", "降低")):
                continue
            key = _slug_key(text)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            items.append(
                {
                    "key": key,
                    "code": key,
                    "name": text[:64],
                    "value": "",
                    "unit": "",
                    "severity": "medium",
                    "reason": "来自报告摘要",
                    "suggestion": "建议结合专科意见定期复查",
                }
            )

    return items


def build_follow_up_tasks_from_abnormals(abnormal_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for item in abnormal_items:
        haystack = " ".join(
            [
                str(item.get("name") or ""),
                str(item.get("code") or ""),
                str(item.get("reason") or ""),
            ]
        ).lower()
        for rule in FOLLOW_UP_RULES:
            if not re.search(rule["pattern"], haystack, flags=re.IGNORECASE):
                continue
            if rule["key"] in seen_keys:
                break
            seen_keys.add(rule["key"])
            tasks.append(
                {
                    "key": rule["key"],
                    "title": rule["title"],
                    "medical_task_type": rule["medical_task_type"],
                    "due_in_days": rule["due_in_days"],
                    "priority": rule["priority"],
                    "source_abnormal_key": item.get("key") or item.get("code"),
                    "source_abnormal_name": item.get("name"),
                }
            )
            break
    return tasks


def _recommended_items_for_context(
    *,
    member: Member,
    profile: MemberMedicalProfile | None,
    abnormal_items: list[dict[str, Any]],
) -> list[dict[str, str]]:
    recommended: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(key: str, name: str) -> None:
        if key in seen:
            return
        seen.add(key)
        recommended.append({"key": key, "name": name})

    haystack = " ".join(str(item.get("name") or "") for item in abnormal_items).lower()
    chronic = " ".join(profile.chronic_conditions if profile else []).lower()
    combined = f"{haystack} {chronic}"

    if re.search(r"甲状腺|tsh|结节", combined):
        add("thyroid_ultrasound", "甲状腺彩超")
    if re.search(r"肝|脂肪肝", combined):
        add("abdominal_ultrasound", "腹部彩超")
    if re.search(r"肺|胸部|吸烟", combined):
        add("chest_ct", "低剂量胸部 CT")
    if re.search(r"心|血压|血脂|ldl", combined):
        add("ecg", "心电图")
    if member.birth_date:
        age = (timezone.localdate() - member.birth_date).days // 365
        if age >= 40:
            add("tumor_markers", "肿瘤标志物筛查")
    if not recommended:
        add("abdominal_ultrasound", "腹部彩超")
    return recommended


def build_exam_plan_payload(
    *,
    member: Member,
    profile: MemberMedicalProfile | None,
    mode: str,
    abnormal_items: list[dict[str, Any]],
    follow_up_tasks: list[dict[str, Any]],
    report: HealthExamReport | None = None,
) -> dict[str, Any]:
    year = timezone.localdate().year
    if mode == "baseline":
        title = f"{year} 年度首次体检清单"
        rationale = ["基础档案", "健康病史", "症状表现", "生活习惯"]
    else:
        title = f"{year} 年度 AI 定制体检单"
        rationale = ["历史报告", "病史", "生活习惯", "症状", "家族史"]
        if report and report.exam_date:
            rationale.insert(0, f"{report.exam_date.year} 年体检报告")

    must_items = [dict(item) for item in BASELINE_MUST_ITEMS]
    recommended_items = _recommended_items_for_context(
        member=member,
        profile=profile,
        abnormal_items=abnormal_items,
    )
    follow_up_items = [
        {"key": task["key"], "name": task["title"], "source": task.get("source_abnormal_name")}
        for task in follow_up_tasks
    ]

    return {
        "title": title,
        "must_items": must_items,
        "recommended_items": recommended_items,
        "follow_up_items": follow_up_items,
        "rationale": rationale,
        "risk_notice": DEFAULT_RISK_NOTICE,
    }


def build_evidence_snapshot(
    *,
    member: Member,
    profile: MemberMedicalProfile | None,
    symptoms: list[Symptom] | None = None,
) -> dict[str, Any]:
    guidance = build_member_medical_guidance_projection(
        member=member,
        profile=profile,
        symptoms=symptoms or [],
    )
    sections = guidance.get("guidance_sections") or {}
    return {
        "basic_profile": sections.get("basic_profile", {}).get("summary"),
        "health_history": sections.get("health_history", {}).get("summary"),
        "symptoms": sections.get("symptoms", {}).get("summary"),
        "lifestyle": sections.get("lifestyle", {}).get("summary"),
        "family_history": (profile.family_history if profile else []) or [],
    }


@transaction.atomic
def save_confirmed_abnormal_items(
    *,
    user,
    member: Member,
    report: HealthExamReport | None,
    abnormal_items: list[dict[str, Any]],
) -> MemberMedicalKeyIndicatorRecord:
    names = [str(item.get("name") or "").strip() for item in abnormal_items if item.get("name")]
    summary = " · ".join(names[:6]) if names else "体检报告异常项确认"
    record = MemberMedicalKeyIndicatorRecord.objects.create(
        user=user,
        member=member,
        source=MemberMedicalKeyIndicatorRecord.Source.REPORT_EXTRACTION,
        scenario=MemberMedicalKeyIndicatorRecord.Scenario.EXAM_PLAN,
        recorded_at=timezone.now(),
        title="体检报告异常项确认",
        summary=summary,
        extra={
            "source_report_id": report.id if report else None,
            "confirmed_abnormal_items": abnormal_items,
        },
    )
    logger.info(
        "confirmed-abnormal-items saved member_id=%s report_id=%s count=%s record_id=%s",
        member.id,
        report.id if report else None,
        len(abnormal_items),
        record.id,
    )
    return record


def _priority_value(priority: str) -> int:
    mapping = {"high": TaskPriority.HIGH, "medium": TaskPriority.MEDIUM, "low": TaskPriority.LOW}
    return mapping.get((priority or "").lower(), TaskPriority.MEDIUM)


def create_follow_up_tasks(
    *,
    user,
    member: Member,
    plan: MemberMedicalExamPlan,
    follow_up_tasks: list[dict[str, Any]],
    selected_keys: list[str] | None,
) -> list[dict[str, Any]]:
    selected = set(selected_keys or [])
    created: list[dict[str, Any]] = []
    for draft in follow_up_tasks:
        key = str(draft.get("key") or "")
        if selected and key not in selected:
            continue
        due_days = int(draft.get("due_in_days") or 90)
        reminder_time = timezone.now() + timedelta(days=due_days)
        task = Task.objects.create(
            member=member,
            creator=user,
            title=str(draft.get("title") or "复查提醒"),
            description=str(draft.get("source_abnormal_name") or ""),
            type=TaskType.MEDICAL,
            status=TaskStatus.PENDING,
            priority=_priority_value(str(draft.get("priority") or "medium")),
            business_type="medical_exam_follow_up",
            business_id=str(plan.id),
            source=TaskSource.AI if plan.source.startswith("ai_") else TaskSource.REPORT,
            due_time=reminder_time,
        )
        TaskMedical.objects.create(
            task=task,
            status=TaskStatus.PENDING,
            reminder_time=reminder_time,
            medical_task_type=str(draft.get("medical_task_type") or "general_follow_up"),
            description=str(draft.get("source_abnormal_name") or ""),
            source="ai_report" if plan.source == MemberMedicalExamPlan.Source.AI_REPORT else "ai_baseline",
            created_by=user,
            operator=user,
        )
        TaskNotification.objects.create(
            task=task,
            member=member,
            status=TaskNotificationStatus.PENDING,
            reminder_time=reminder_time,
            template_code="health_task_default",
            template_params={
                "title": "健康任务提醒",
                "content": f"你有一个待完成任务：{task.title}",
                "task_id": task.id,
            },
        )
        created.append(
            {
                "task_id": task.id,
                "key": key,
                "title": task.title,
                "reminder_time": reminder_time.isoformat(),
            }
        )
    logger.info("exam-plan created follow-up tasks count=%s member_id=%s plan_id=%s", len(created), member.id, plan.id)
    return created


def _plan_summary_text(plan_payload: dict[str, Any]) -> str:
    must = plan_payload.get("must_items") or []
    recommended = plan_payload.get("recommended_items") or []
    pieces = [str(plan_payload.get("title") or "AI 定制体检单")]
    if must:
        pieces.append(f"必做 {len(must)} 项")
    if recommended:
        pieces.append(f"建议增加 {len(recommended)} 项")
    return " · ".join(pieces)


def _update_profile_projection(
    *,
    user,
    member: Member,
    plan: MemberMedicalExamPlan,
    plan_payload: dict[str, Any],
) -> MemberMedicalProfile:
    profile, _ = MemberMedicalProfile.objects.get_or_create(user=user, member=member, defaults={"extra": {}})
    extra = dict(profile.extra or {})
    extra["exam_plan_summary"] = _plan_summary_text(plan_payload)
    extra["latest_exam_plan_id"] = str(plan.id)
    profile.extra = extra
    profile.save(update_fields=["extra", "updated_at"])
    logger.info("exam-plan updated MemberMedicalProfile member_id=%s plan_id=%s", member.id, plan.id)
    return profile


@transaction.atomic
def generate_exam_archive_ai_plan(
    *,
    user,
    member: Member,
    mode: str,
    report: HealthExamReport | None,
    selected_abnormal_items: list[dict[str, Any]] | None,
    create_follow_up_tasks_flag: bool,
    selected_follow_up_task_keys: list[str] | None,
    client_plan_payload: dict[str, Any] | None = None,
    ai_trace_id: str = "",
    model_name: str = "",
) -> dict[str, Any]:
    profile = (
        MemberMedicalProfile.objects.filter(is_deleted=False, member_id=member.id, user=user)
        .order_by("-updated_at", "-id")
        .first()
    )
    abnormal_items = list(selected_abnormal_items or [])
    if not abnormal_items and report is not None:
        abnormal_items = extract_abnormal_items_from_report(report=report)

    follow_up_tasks = build_follow_up_tasks_from_abnormals(abnormal_items)
    if client_plan_payload:
        plan_payload = dict(client_plan_payload)
        plan_payload.setdefault("risk_notice", DEFAULT_RISK_NOTICE)
    else:
        plan_payload = build_exam_plan_payload(
            member=member,
            profile=profile,
            mode=mode,
            abnormal_items=abnormal_items,
            follow_up_tasks=follow_up_tasks,
            report=report,
        )

    source = (
        MemberMedicalExamPlan.Source.AI_BASELINE
        if mode == "baseline"
        else MemberMedicalExamPlan.Source.AI_REPORT
    )
    plan = MemberMedicalExamPlan.objects.create(
        user=user,
        member=member,
        source=source,
        status=MemberMedicalExamPlan.Status.CONFIRMED,
        source_report=report,
        title=str(plan_payload.get("title") or "AI 定制体检单"),
        must_items=plan_payload.get("must_items") or [],
        recommended_items=plan_payload.get("recommended_items") or [],
        follow_up_items=plan_payload.get("follow_up_items") or [],
        rationale=plan_payload.get("rationale") or [],
        risk_notice=str(plan_payload.get("risk_notice") or DEFAULT_RISK_NOTICE),
        ai_trace_id=ai_trace_id or "",
        model_name=model_name or "",
        extra={"mode": mode, "abnormal_count": len(abnormal_items)},
    )

    created_tasks: list[dict[str, Any]] = []
    if create_follow_up_tasks_flag:
        created_tasks = create_follow_up_tasks(
            user=user,
            member=member,
            plan=plan,
            follow_up_tasks=follow_up_tasks,
            selected_keys=selected_follow_up_task_keys,
        )

    profile = _update_profile_projection(user=user, member=member, plan=plan, plan_payload=plan_payload)

    return {
        "mode": mode,
        "member_id": member.id,
        "source_report_id": report.id if report else None,
        "plan_id": plan.id,
        "plan": plan,
        "profile": profile,
        "abnormal_items": abnormal_items,
        "follow_up_tasks": follow_up_tasks,
        "created_tasks": created_tasks,
        "exam_plan": {
            "id": plan.id,
            "title": plan.title,
            "must_items": plan.must_items,
            "recommended_items": plan.recommended_items,
            "follow_up_items": plan.follow_up_items,
            "rationale": plan.rationale,
            "risk_notice": plan.risk_notice,
        },
    }
