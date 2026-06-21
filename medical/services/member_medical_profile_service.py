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
