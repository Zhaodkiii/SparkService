from __future__ import annotations

from django.contrib.auth.models import User

from medical.models import MemberMedicalProfile, Symptom


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
