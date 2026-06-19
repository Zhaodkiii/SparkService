"""饮食目标与身体指标统一计算服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.contrib.auth.models import User

from medical.models import Member
from nutrition.models import NutritionEnergyBurnRecord


FORMULA_NAME = "mifflin_st_jeor"
FORMULA_VERSION = "v1"
ENERGY_PER_KG = Decimal("7700")
MIN_SAFE_ENERGY_KCAL = Decimal("1200")

ACTIVITY_FACTORS = {
    "low": Decimal("1.2"),
    "medium": Decimal("1.375"),
    "high": Decimal("1.55"),
    "very_high": Decimal("1.725"),
}

GOAL_WEEKLY_DEFAULTS = {
    "lose_weight": Decimal("-0.50"),
    "maintain": Decimal("0"),
    "gain_weight": Decimal("0.25"),
    "gain_muscle": Decimal("0.25"),
    "build_muscle": Decimal("0.25"),
    "control_sugar": Decimal("0"),
    "control_salt": Decimal("0"),
    "control_fat": Decimal("0"),
    "custom": Decimal("0"),
}


def _q(value: Decimal | float | int | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


@dataclass(frozen=True)
class GoalCalculationInput:
    user: User
    member_id: int
    goal_type: str
    activity_level: str
    current_weight_kg: Decimal | None = None
    height_cm: Decimal | None = None
    biological_sex: str | None = None
    age_years: int | None = None
    weekly_weight_delta_kg: Decimal | None = None
    target_weight_kg: Decimal | None = None


def calculate_body_metrics(payload: GoalCalculationInput) -> dict[str, Any]:
    member = Member.objects.filter(id=payload.member_id, is_deleted=False).first()
    biological_sex = _normalize_sex(payload.biological_sex or (member.gender if member else ""))
    age_years = payload.age_years or _age_from_birth_date(member.birth_date if member else None)
    height_cm = _q(payload.height_cm)
    current_weight_kg = _q(payload.current_weight_kg)
    weekly_weight_delta_kg = _q(payload.weekly_weight_delta_kg)
    if weekly_weight_delta_kg is None:
        weekly_weight_delta_kg = GOAL_WEEKLY_DEFAULTS.get(payload.goal_type, Decimal("0"))
    activity_level = payload.activity_level or "low"
    activity_factor = ACTIVITY_FACTORS.get(activity_level)

    missing_fields: list[str] = []
    if biological_sex not in {"male", "female"}:
        missing_fields.append("biological_sex")
    if age_years is None:
        missing_fields.append("age_years")
    if height_cm is None or height_cm <= 0:
        missing_fields.append("height_cm")
    if current_weight_kg is None or current_weight_kg <= 0:
        missing_fields.append("current_weight_kg")
    if activity_factor is None:
        missing_fields.append("activity_level")

    warnings: list[str] = []
    risk_flags: list[str] = []
    bmi = None
    ideal_weight = None
    calorie_intake = None
    calories_burned = None

    if not missing_fields:
        assert height_cm is not None
        assert current_weight_kg is not None
        assert age_years is not None
        assert activity_factor is not None
        height_m = height_cm / Decimal("100")
        bmi_value = _q(current_weight_kg / (height_m * height_m))
        bmi = {
            "value": _float(bmi_value),
            "category": _bmi_category(bmi_value),
            "category_text": _bmi_category_text(bmi_value),
        }
        ideal_min = _q(Decimal("18.5") * height_m * height_m)
        ideal_max = _q(Decimal("24.0") * height_m * height_m)
        reference = _q(height_cm - Decimal("100"))
        ideal_weight = {
            "min_kg": _float(ideal_min),
            "max_kg": _float(ideal_max),
            "reference_kg": _float(reference),
            "method": "bmi_range_broca_reference",
            "target_weight_status": _target_weight_status(_q(payload.target_weight_kg), ideal_min, ideal_max),
        }
        bmr = _calculate_bmr(biological_sex, current_weight_kg, height_cm, age_years)
        tdee = _q(bmr * activity_factor)
        daily_delta = _q(weekly_weight_delta_kg * ENERGY_PER_KG / Decimal("7"))
        suggested = _q(tdee + daily_delta)
        if suggested is not None and suggested < MIN_SAFE_ENERGY_KCAL:
            risk_flags.append("below_safe_energy_floor")
            warnings.append("unsafe_energy_goal")
        calculation_inputs = {
            "activity_factor": _float(activity_factor),
            "weekly_weight_energy_kcal_per_kg": float(ENERGY_PER_KG),
            "min_safe_energy_kcal": float(MIN_SAFE_ENERGY_KCAL),
            "risk_flags": risk_flags,
            "missing_fields": [],
            "used_default_values": payload.weekly_weight_delta_kg is None,
            "source": "goal_recalculate",
        }
        calorie_intake = {
            "suggested_energy_kcal": _float(suggested),
            "bmr_kcal": _float(bmr),
            "tdee_kcal": _float(tdee),
            "energy_delta_kcal": _float(daily_delta),
            "calculation_formula": FORMULA_NAME,
            "calculation_version": FORMULA_VERSION,
            "calculation_inputs": calculation_inputs,
            "reason": "tdee_plus_goal_delta",
        }
        estimated_activity = _q(tdee - bmr)
        calories_burned = {
            "bmr_kcal": _float(bmr),
            "tdee_kcal": _float(tdee),
            "estimated_daily_activity_kcal": _float(estimated_activity),
            "apple_health_active_energy_kcal": _float(_today_burned(payload.user, payload.member_id, "active_energy")),
            "manual_burned_energy_kcal": _float(_today_manual_burned(payload.user, payload.member_id)),
            "source": "estimated",
        }

    calculation_inputs = {
        "activity_factor": _float(activity_factor) if activity_factor else None,
        "weekly_weight_energy_kcal_per_kg": float(ENERGY_PER_KG),
        "min_safe_energy_kcal": float(MIN_SAFE_ENERGY_KCAL),
        "risk_flags": risk_flags,
        "missing_fields": missing_fields,
        "used_default_values": payload.weekly_weight_delta_kg is None,
        "source": "goal_recalculate",
    }
    return {
        "bmi": bmi,
        "ideal_weight": ideal_weight,
        "calorie_intake": calorie_intake,
        "calories_burned": calories_burned,
        "missing_fields": missing_fields,
        "warnings": warnings,
        "calculation_formula": FORMULA_NAME,
        "calculation_version": FORMULA_VERSION,
        "calculation_inputs": calculation_inputs,
    }


def calculate_energy(payload: GoalCalculationInput) -> dict[str, Any]:
    result = calculate_body_metrics(payload)
    if result["calorie_intake"]:
        return result["calorie_intake"]
    return {
        "suggested_energy_kcal": None,
        "bmr_kcal": None,
        "tdee_kcal": None,
        "energy_delta_kcal": None,
        "calculation_formula": FORMULA_NAME,
        "calculation_version": FORMULA_VERSION,
        "calculation_inputs": result["calculation_inputs"],
        "reason": "missing_required_profile_fields",
    }


def _normalize_sex(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"male", "female"}:
        return normalized
    return "unknown"


def _age_from_birth_date(birth_date: date | None) -> int | None:
    if birth_date is None:
        return None
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return max(age, 0)


def _calculate_bmr(sex: str, weight_kg: Decimal, height_cm: Decimal, age_years: int) -> Decimal:
    base = Decimal("10") * weight_kg + Decimal("6.25") * height_cm - Decimal("5") * Decimal(age_years)
    if sex == "female":
        return _q(base - Decimal("161")) or Decimal("0")
    return _q(base + Decimal("5")) or Decimal("0")


def _bmi_category(value: Decimal | None) -> str:
    if value is None:
        return "unknown"
    if value < Decimal("18.5"):
        return "underweight"
    if value < Decimal("24"):
        return "normal"
    if value < Decimal("28"):
        return "overweight"
    return "obese"


def _bmi_category_text(value: Decimal | None) -> str:
    return {
        "underweight": "偏瘦",
        "normal": "正常",
        "overweight": "超重",
        "obese": "肥胖",
        "unknown": "未知",
    }[_bmi_category(value)]


def _target_weight_status(target_weight: Decimal | None, min_kg: Decimal | None, max_kg: Decimal | None) -> str:
    if target_weight is None or min_kg is None or max_kg is None:
        return "unknown"
    if target_weight < min_kg:
        return "below_range"
    if target_weight > max_kg:
        return "above_range"
    return "within_range"


def _today_burned(user: User, member_id: int, activity_type: str) -> Decimal:
    today = date.today()
    total = Decimal("0")
    records = NutritionEnergyBurnRecord.objects.filter(
        user=user,
        member_id=member_id,
        local_day=today,
        source=NutritionEnergyBurnRecord.Source.APPLE_HEALTH_IMPORT,
        activity_type=activity_type,
    )
    for record in records:
        total += record.energy_kcal
    return _q(total) or Decimal("0")


def _today_manual_burned(user: User, member_id: int) -> Decimal:
    today = date.today()
    total = Decimal("0")
    records = NutritionEnergyBurnRecord.objects.filter(
        user=user,
        member_id=member_id,
        local_day=today,
        source=NutritionEnergyBurnRecord.Source.MANUAL,
    )
    for record in records:
        total += record.energy_kcal
    return _q(total) or Decimal("0")
