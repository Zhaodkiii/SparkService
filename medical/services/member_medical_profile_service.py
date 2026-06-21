from __future__ import annotations

from django.contrib.auth.models import User

from medical.models import MedicationPlan, MemberMedicalProfile, Surgery, Symptom


def extract_symptom_focus_names(symptoms) -> list[str]:
    """从有效症状记录提取成员症状关注摘要（去重、保序）。"""
    names: list[str] = []
    seen: set[str] = set()
    for symptom in symptoms:
        raw_name = (getattr(symptom, "name", None) or "").strip()
        if not raw_name:
            continue
        parts = [part.strip() for part in raw_name.split("、") if part.strip()]
        if not parts:
            parts = [raw_name]
        for part in parts:
            if part in seen:
                continue
            seen.add(part)
            names.append(part)
    return names


def build_symptom_follow_up_summary(focus_names: list[str]) -> str:
    return " · ".join(focus_names)


def recompute_symptom_follow_up_focus(*, user: User, member_id: int) -> tuple[MemberMedicalProfile | None, list[str], str]:
    """
    根据成员有效 Symptom 明细重算 MemberMedicalProfile.symptom_follow_up_focus。

    返回 (profile, focus_names, summary_text)。
    """
    symptoms = (
        Symptom.objects.filter(member_id=member_id, is_deleted=False)
        .order_by("-updated_at", "-created_at", "-id")
    )
    focus_names = extract_symptom_focus_names(symptoms)
    summary = build_symptom_follow_up_summary(focus_names)

    profile = (
        MemberMedicalProfile.objects.filter(user=user, member_id=member_id, is_deleted=False)
        .order_by("-updated_at", "-id")
        .first()
    )

    if profile is None:
        if not focus_names:
            return None, focus_names, summary
        profile = MemberMedicalProfile.objects.create(
            user=user,
            member_id=member_id,
            symptom_follow_up_focus=focus_names,
        )
        return profile, focus_names, summary

    if profile.symptom_follow_up_focus != focus_names:
        profile.symptom_follow_up_focus = focus_names
        profile.save(update_fields=["symptom_follow_up_focus", "updated_at"])

    return profile, focus_names, summary


def build_symptom_mutation_payload(
    *,
    user: User,
    member_id: int,
    symptom=None,
    deleted: bool = False,
) -> dict:
    profile, _focus_names, summary = recompute_symptom_follow_up_focus(user=user, member_id=member_id)
    from medical.serializers import MemberMedicalProfileSerializer, SymptomSerializer

    payload = {
        "deleted": deleted,
        "symptom": SymptomSerializer(symptom).data if symptom is not None else None,
        "summary": summary,
        "member_profile": MemberMedicalProfileSerializer(profile).data if profile is not None else None,
    }
    return payload


ACTIVE_MEDICATION_PLAN_STATUSES = ("active", "paused")


def _medication_plan_dose_summary(plan: MedicationPlan) -> str:
    dose = (plan.dose_per_time or "").strip()
    if dose:
        return dose
    if plan.dose_value is not None and (plan.dose_unit or "").strip():
        normalized = str(plan.dose_value).rstrip("0").rstrip(".")
        return f"{normalized}{plan.dose_unit.strip()}"
    return ""


def build_medication_plan_summary(plan: MedicationPlan) -> str:
    parts: list[str] = []
    dose = _medication_plan_dose_summary(plan)
    if dose:
        parts.append(dose)
    frequency = (plan.frequency_text or "").strip()
    if frequency:
        parts.append(frequency)
    if plan.status == MedicationPlan.Status.PAUSED:
        parts.append("已暂停")
    elif plan.reminder_enabled and isinstance(plan.reminder_times, list):
        times = [str(item.get("time", "")).strip() for item in plan.reminder_times if isinstance(item, dict)]
        times = [time for time in times if time]
        if times:
            parts.append(f"{times[0]}提醒")
    return " · ".join(parts)


def medication_plan_to_focus_item(plan: MedicationPlan) -> dict:
    return {
        "drug_name": (plan.drug_name or "").strip(),
        "summary": build_medication_plan_summary(plan),
        "status": plan.status,
        "reminder_enabled": bool(plan.reminder_enabled),
        "source_plan_id": plan.id,
    }


def build_medication_focus_summary(focus_items: list[dict]) -> str:
    if not focus_items:
        return "暂无长期用药"
    lines: list[str] = []
    for item in focus_items:
        drug_name = (item.get("drug_name") or "").strip()
        if not drug_name:
            continue
        summary = (item.get("summary") or "").strip()
        lines.append(f"{drug_name} · {summary}" if summary else drug_name)
    return " / ".join(lines) if lines else "暂无长期用药"


def recompute_medication_focus(*, user: User, member_id: int) -> tuple[MemberMedicalProfile | None, list[dict], str]:
    plans = list(
        MedicationPlan.objects.filter(
            member_id=member_id,
            is_deleted=False,
            status__in=ACTIVE_MEDICATION_PLAN_STATUSES,
        )
    )
    active_plans = sorted(
        plans,
        key=lambda plan: (
            0 if plan.status == MedicationPlan.Status.ACTIVE else 1,
            0 if plan.reminder_enabled else 1,
            -(plan.start_date.toordinal() if plan.start_date else 0),
            -(plan.updated_at.timestamp() if plan.updated_at else 0),
            -plan.id,
        ),
    )

    focus_items = [medication_plan_to_focus_item(plan) for plan in active_plans if (plan.drug_name or "").strip()]
    summary = build_medication_focus_summary(focus_items)

    profile = (
        MemberMedicalProfile.objects.filter(user=user, member_id=member_id, is_deleted=False)
        .order_by("-updated_at", "-id")
        .first()
    )

    if profile is None:
        if not focus_items:
            return None, focus_items, summary
        profile = MemberMedicalProfile.objects.create(
            user=user,
            member_id=member_id,
            medication_focus=focus_items,
        )
        return profile, focus_items, summary

    if profile.medication_focus != focus_items:
        profile.medication_focus = focus_items
        profile.save(update_fields=["medication_focus", "updated_at"])

    return profile, focus_items, summary


def build_medication_mutation_payload(
    *,
    user: User,
    member_id: int,
    medication_plan=None,
    deleted: bool = False,
) -> dict:
    profile, _focus_items, summary = recompute_medication_focus(user=user, member_id=member_id)
    from medical.serializers import MemberMedicalProfileSerializer, MedicationPlanSerializer

    payload = {
        "deleted": deleted,
        "medication_plan": MedicationPlanSerializer(medication_plan).data if medication_plan is not None else None,
        "summary": summary,
        "member_profile": MemberMedicalProfileSerializer(profile).data if profile is not None else None,
    }
    return payload


def _surgery_time_text(surgery: Surgery) -> str:
    if surgery.performed_at:
        return f"{surgery.performed_at.year}年{surgery.performed_at.month}月"
    extra = surgery.extra or {}
    for key in ("performed_at_text", "surgery_time"):
        value = (extra.get(key) or "").strip()
        if value:
            return value
    return ""


def build_surgery_summary_line(surgery: Surgery) -> str:
    parts: list[str] = []
    time_text = _surgery_time_text(surgery)
    if time_text:
        parts.append(time_text)
    site = (surgery.site or "").strip()
    if site:
        parts.append(site)
    extra = surgery.extra or {}
    hospital = (extra.get("hospital_name") or "").strip()
    if hospital:
        parts.append(hospital)
    recovery = (extra.get("recovery_status") or "").strip()
    if recovery:
        parts.append(recovery)
    return " · ".join(parts)


def surgery_to_focus_item(surgery: Surgery) -> dict:
    performed_at = surgery.performed_at.isoformat() if surgery.performed_at else None
    return {
        "procedure_name": (surgery.procedure_name or "").strip(),
        "summary": build_surgery_summary_line(surgery),
        "performed_at": performed_at,
        "site": (surgery.site or "").strip(),
        "source_surgery_id": surgery.id,
    }


def build_surgery_focus_summary(focus_items: list[dict]) -> str:
    if not focus_items:
        return "无手术史"
    lines: list[str] = []
    for item in focus_items:
        name = (item.get("procedure_name") or "").strip()
        if not name:
            continue
        summary = (item.get("summary") or "").strip()
        lines.append(f"{name} · {summary}" if summary else name)
    return " / ".join(lines) if lines else "无手术史"


def recompute_surgery_focus(*, user: User, member_id: int) -> tuple[MemberMedicalProfile | None, list[dict], str]:
    surgeries = list(
        Surgery.objects.filter(member_id=member_id, is_deleted=False).order_by(
            "-performed_at",
            "-updated_at",
            "-id",
        )
    )
    focus_items = [surgery_to_focus_item(row) for row in surgeries if (row.procedure_name or "").strip()]
    summary = build_surgery_focus_summary(focus_items)

    profile = (
        MemberMedicalProfile.objects.filter(user=user, member_id=member_id, is_deleted=False)
        .order_by("-updated_at", "-id")
        .first()
    )

    if profile is None:
        if not focus_items:
            return None, focus_items, summary
        profile = MemberMedicalProfile.objects.create(
            user=user,
            member_id=member_id,
            surgery_focus=focus_items,
        )
        return profile, focus_items, summary

    if profile.surgery_focus != focus_items:
        profile.surgery_focus = focus_items
        profile.save(update_fields=["surgery_focus", "updated_at"])

    return profile, focus_items, summary


def build_surgery_mutation_payload(
    *,
    user: User,
    member_id: int,
    surgery=None,
    deleted: bool = False,
) -> dict:
    profile, _focus_items, summary = recompute_surgery_focus(user=user, member_id=member_id)
    from medical.serializers import MemberMedicalProfileSerializer, SurgerySerializer

    payload = {
        "deleted": deleted,
        "surgery": SurgerySerializer(surgery).data if surgery is not None else None,
        "summary": summary,
        "member_profile": MemberMedicalProfileSerializer(profile).data if profile is not None else None,
    }
    return payload


def _gender_display(gender: str) -> str:
    return {"male": "男", "female": "女"}.get((gender or "").strip(), "未选择")


def _member_age_text(birth_date) -> str | None:
    if birth_date is None:
        return None
    from django.utils import timezone

    today = timezone.localdate()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return f"{age}岁"


def _section_status(has_content: bool, is_completed: bool) -> str:
    if is_completed:
        return "completed"
    if has_content:
        return "in_progress"
    return "not_started"


def _extra_value(extra: dict | None, *keys: str) -> str:
    if not extra:
        return ""
    for key in keys:
        value = (extra.get(key) or "").strip()
        if value:
            return value
    return ""


def build_member_medical_guidance_projection(
    *,
    member,
    profile,
    symptoms=None,
    medication_plans=None,
    surgeries=None,
    health_exam_reports=None,
    examination_reports=None,
) -> dict:
    """
    聚合医疗引导分组摘要，供 complete-data / member-guidance 共用。
    """
    from django.utils import timezone

    extra = dict(profile.extra or {}) if profile is not None else {}
    symptoms = list(symptoms or [])
    medication_plans = list(medication_plans or [])
    surgeries = list(surgeries or [])
    health_exam_reports = list(health_exam_reports or [])
    examination_reports = list(examination_reports or [])

    height_text = _extra_value(extra, "height_cm")
    weight_text = _extra_value(extra, "weight_kg")
    occupation = _extra_value(extra, "occupation")
    sedentary = _extra_value(extra, "sedentary_hours_level", "sedentary_level")

    basic_pieces: list[str] = []
    if member and (member.gender or "").strip() not in {"", "unknown"}:
        basic_pieces.append(_gender_display(member.gender))
    age_text = _member_age_text(getattr(member, "birth_date", None))
    if age_text:
        basic_pieces.append(age_text)
    if height_text:
        try:
            basic_pieces.append(f"{float(height_text):.0f}cm")
        except ValueError:
            basic_pieces.append(f"{height_text}cm")
    if weight_text:
        try:
            basic_pieces.append(f"{float(weight_text):.0f}kg")
        except ValueError:
            basic_pieces.append(f"{weight_text}kg")
    if occupation:
        basic_pieces.append(occupation)
    if sedentary:
        sedentary_labels = {"low": "低久坐", "medium": "中久坐", "high": "高久坐"}
        basic_pieces.append(sedentary_labels.get(sedentary, sedentary))

    basic_completed = (
        (member.gender or "").strip() not in {"", "unknown"}
        and getattr(member, "birth_date", None) is not None
        and bool(height_text)
        and bool(weight_text)
        and bool(sedentary)
    )
    basic_summary = " · ".join(basic_pieces) if basic_pieces else "待补充"

    history_pieces: list[str] = []
    if profile is not None:
        if profile.symptom_follow_up_focus:
            history_pieces.extend(profile.symptom_follow_up_focus)
        elif symptoms:
            history_pieces.extend(extract_symptom_focus_names(symptoms))
        if profile.chronic_conditions:
            history_pieces.extend(profile.chronic_conditions)
        if profile.medication_focus:
            for item in profile.medication_focus:
                drug_name = (item.get("drug_name") or "").strip()
                if drug_name:
                    history_pieces.append(drug_name)
        elif medication_plans:
            for plan in medication_plans:
                if plan.status in ACTIVE_MEDICATION_PLAN_STATUSES:
                    drug_name = (plan.drug_name or "").strip()
                    if drug_name:
                        history_pieces.append(drug_name)
        if profile.surgery_focus:
            for item in profile.surgery_focus:
                name = (item.get("procedure_name") or "").strip()
                if name:
                    history_pieces.append(name)
        elif surgeries:
            for row in surgeries:
                name = (row.procedure_name or "").strip()
                if name:
                    history_pieces.append(name)
        if profile.allergies:
            history_pieces.extend(profile.allergies)

    history_has_content = bool(history_pieces) or any(
        _extra_value(extra, key)
        for key in (
            "chronic_condition_status",
            "long_term_medication_status",
            "surgery_status",
            "allergy_status",
            "family_history_screening_status",
            "symptom_follow_up_status",
        )
    )
    history_completed = history_has_content and _extra_value(extra, "symptom_follow_up_status") not in {"", "unknown"}
    history_summary = " · ".join(dict.fromkeys(history_pieces)) if history_pieces else "待补充"

    lifestyle_pieces: list[str] = []
    if profile is not None:
        smoking = profile.smoking_profile or {}
        drinking = profile.drinking_profile or {}
        exercise = profile.exercise_profile or {}
        if (smoking.get("status") or "").strip() not in {"", "never"}:
            lifestyle_pieces.append("吸烟")
        if (drinking.get("status") or "").strip() not in {"", "none"}:
            lifestyle_pieces.append("饮酒")
        if (exercise.get("frequency") or "").strip() not in {"", "none"}:
            lifestyle_pieces.append("运动")
        if profile.sleep_hours is not None:
            lifestyle_pieces.append(f"{profile.sleep_hours:.0f}小时睡眠")
    lifestyle_has_content = bool(lifestyle_pieces)
    lifestyle_summary = " · ".join(lifestyle_pieces) if lifestyle_pieces else "待补充"

    exam_pieces: list[str] = []
    if _extra_value(extra, "has_exam_history") in {"1", "true", "True", "yes"}:
        exam_pieces.append("有体检史")
    last_exam_year = _extra_value(extra, "last_exam_year")
    if last_exam_year:
        exam_pieces.append(last_exam_year)
    if health_exam_reports:
        latest = health_exam_reports[0]
        exam_date = getattr(latest, "exam_date", None)
        if exam_date:
            exam_pieces.append(f"{exam_date.year}年体检")
    if examination_reports:
        exam_pieces.append("有检查报告")
    exam_plan_summary = _extra_value(extra, "exam_plan_summary")
    if not exam_plan_summary and profile is not None and profile.exam_focus:
        exam_plan_summary = " · ".join(profile.exam_focus)
    exam_has_content = bool(exam_pieces) or bool(exam_plan_summary) or bool(health_exam_reports or examination_reports)
    exam_summary = " · ".join(exam_pieces) if exam_pieces else ("未填写" if not exam_has_content else "已填写")

    risk_assessment_summary = _extra_value(extra, "risk_assessment_summary")
    if not risk_assessment_summary and profile is not None and profile.notes:
        risk_assessment_summary = profile.notes.strip()
    risk_has_content = bool(risk_assessment_summary)

    guidance_sections = [
        {
            "section_code": "basic_profile",
            "title": "基础档案",
            "summary": basic_summary,
            "status": _section_status(bool(basic_pieces), basic_completed),
        },
        {
            "section_code": "health_history",
            "title": "健康病史与症状记录",
            "summary": history_summary,
            "status": _section_status(history_has_content, history_completed),
        },
        {
            "section_code": "lifestyle",
            "title": "生活习惯",
            "summary": lifestyle_summary,
            "status": _section_status(lifestyle_has_content, lifestyle_has_content),
        },
        {
            "section_code": "exam_archive",
            "title": "过往体检档案",
            "summary": exam_summary if not exam_plan_summary else f"{exam_summary} · {exam_plan_summary}",
            "status": _section_status(exam_has_content, exam_has_content),
        },
        {
            "section_code": "risk_assessment",
            "title": "风险评估",
            "summary": risk_assessment_summary or "待生成",
            "status": _section_status(risk_has_content, risk_has_content),
        },
    ]

    guidance_updated_at = timezone.now()
    if profile is not None and profile.updated_at:
        guidance_updated_at = profile.updated_at

    return {
        "guidance_sections": guidance_sections,
        "risk_assessment_summary": risk_assessment_summary or None,
        "exam_plan_summary": exam_plan_summary or None,
        "guidance_updated_at": guidance_updated_at,
    }


def enrich_member_medical_profile_payload(base_payload: dict | None, projection: dict) -> dict | None:
    if base_payload is None:
        return None
    enriched = dict(base_payload)
    enriched.update(projection)
    return enriched
