"""营养目标读取与默认目标计算。"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.contrib.auth.models import User

from nutrition.constants import (
    DEFAULT_DAILY_GOAL,
    DEFAULT_GOAL_TYPE,
    DEFAULT_MEAL_DISTRIBUTION,
)
from nutrition.models import NutritionGoal


GOAL_TARGET_SAFETY_VERSION = "goal_target_safety_v1"
MAX_DAILY_ENERGY_TARGET_KCAL = Decimal("10000.00")
MAX_MACRO_TARGET_G = Decimal("2000.00")


def _quantize(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return min(max(value, lower), upper)


def _safe_energy(value: Decimal | float | int) -> Decimal:
    return _clamp(_quantize(value), Decimal("0"), MAX_DAILY_ENERGY_TARGET_KCAL)


def _safe_macro(value: Decimal | float | int) -> Decimal:
    return _clamp(_quantize(value), Decimal("0"), MAX_MACRO_TARGET_G)


def get_active_goal(user: User, member_id: int) -> NutritionGoal | None:
    return (
        NutritionGoal.objects.filter(
            user=user,
            member_id=member_id,
            is_active=True,
        )
        .order_by("-effective_from", "-id")
        .first()
    )


def resolve_daily_goal(user: User, member_id: int) -> dict[str, Decimal]:
    goal = get_active_goal(user, member_id)
    if goal is None:
        return {key: _quantize(value) for key, value in DEFAULT_DAILY_GOAL.items()}

    return {
        "energy_kcal": _safe_energy(goal.daily_energy_target_kcal or DEFAULT_DAILY_GOAL["energy_kcal"]),
        "protein_g": _safe_macro(goal.protein_target_g or DEFAULT_DAILY_GOAL["protein_g"]),
        "carbohydrate_g": _safe_macro(goal.carbohydrate_target_g or DEFAULT_DAILY_GOAL["carbohydrate_g"]),
        "fat_g": _safe_macro(goal.fat_target_g or DEFAULT_DAILY_GOAL["fat_g"]),
    }


def resolve_meal_distribution(user: User, member_id: int) -> dict[str, Decimal]:
    goal = get_active_goal(user, member_id)
    raw = goal.meal_distribution if goal and goal.meal_distribution else DEFAULT_MEAL_DISTRIBUTION
    distribution: dict[str, Decimal] = {}
    for meal_type in ("breakfast", "lunch", "dinner", "snack"):
        distribution[meal_type] = _quantize(raw.get(meal_type, DEFAULT_MEAL_DISTRIBUTION[meal_type]))
    return distribution


def resolve_goal_payload(user: User, member_id: int) -> dict[str, Any]:
    daily = resolve_daily_goal(user, member_id)
    goal = get_active_goal(user, member_id)
    return {
        "goal_type": goal.goal_type if goal else DEFAULT_GOAL_TYPE,
        "energy_kcal": float(daily["energy_kcal"]),
        "protein_g": float(daily["protein_g"]),
        "carbohydrate_g": float(daily["carbohydrate_g"]),
        "fat_g": float(daily["fat_g"]),
        "meal_distribution": {key: float(value) for key, value in resolve_meal_distribution(user, member_id).items()},
    }


def resolve_meal_macro_targets(user: User, member_id: int) -> dict[str, dict[str, float]]:
    daily = resolve_daily_goal(user, member_id)
    distribution = resolve_meal_distribution(user, member_id)
    result: dict[str, dict[str, float]] = {}
    for meal_type, ratio in distribution.items():
        result[meal_type] = {
            "target_energy_kcal": float(_quantize(daily["energy_kcal"] * ratio)),
            "target_protein_g": float(_quantize(daily["protein_g"] * ratio)),
            "target_carbohydrate_g": float(_quantize(daily["carbohydrate_g"] * ratio)),
            "target_fat_g": float(_quantize(daily["fat_g"] * ratio)),
        }
    return result


def upsert_goal(
    user: User,
    member_id: int,
    *,
    goal_type: str,
    height_cm: Decimal | float | int | None = None,
    current_weight_kg: Decimal | float | int | None = None,
    target_weight_kg: Decimal | float | int | None = None,
    biological_sex: str = "",
    age_years: int | None = None,
    activity_level: str = "",
    weekly_weight_delta_kg: Decimal | float | int | None = None,
    bmr_kcal: Decimal | float | int | None = None,
    tdee_kcal: Decimal | float | int | None = None,
    energy_delta_kcal: Decimal | float | int | None = None,
    calculation_formula: str = "",
    calculation_version: str = "",
    calculation_inputs: dict[str, Any] | None = None,
    is_energy_target_custom: bool = False,
    weekend_energy_target_kcal: Decimal | float | int | None = None,
    is_weekend_energy_enabled: bool = False,
    step_target: int | None = None,
    daily_energy_target_kcal: Decimal | float | int | None,
    carbohydrate_target_g: Decimal | float | int | None,
    protein_target_g: Decimal | float | int | None,
    fat_target_g: Decimal | float | int | None,
    meal_distribution: dict[str, float] | None,
    effective_from=None,
    is_active: bool = True,
) -> NutritionGoal:
    goal = get_active_goal(user, member_id)
    if goal is None:
        goal = NutritionGoal(user=user, member_id=member_id)
    goal.goal_type = goal_type or DEFAULT_GOAL_TYPE
    goal.height_cm = _quantize(height_cm) if height_cm is not None else None
    goal.current_weight_kg = _quantize(current_weight_kg) if current_weight_kg is not None else None
    goal.target_weight_kg = _quantize(target_weight_kg) if target_weight_kg is not None else None
    goal.biological_sex = biological_sex or ""
    goal.age_years = age_years
    goal.activity_level = activity_level or ""
    goal.weekly_weight_delta_kg = _quantize(weekly_weight_delta_kg) if weekly_weight_delta_kg is not None else None
    goal.bmr_kcal = _quantize(bmr_kcal) if bmr_kcal is not None else None
    goal.tdee_kcal = _quantize(tdee_kcal) if tdee_kcal is not None else None
    goal.energy_delta_kcal = _quantize(energy_delta_kcal) if energy_delta_kcal is not None else None
    goal.calculation_formula = calculation_formula or ""
    goal.calculation_version = calculation_version or ""
    goal.calculation_inputs = calculation_inputs or {}
    goal.is_energy_target_custom = is_energy_target_custom
    goal.weekend_energy_target_kcal = _quantize(weekend_energy_target_kcal) if weekend_energy_target_kcal is not None else None
    goal.is_weekend_energy_enabled = is_weekend_energy_enabled
    goal.step_target = step_target
    goal.daily_energy_target_kcal = _quantize(daily_energy_target_kcal) if daily_energy_target_kcal is not None else None
    goal.carbohydrate_target_g = _quantize(carbohydrate_target_g) if carbohydrate_target_g is not None else None
    goal.protein_target_g = _quantize(protein_target_g) if protein_target_g is not None else None
    goal.fat_target_g = _quantize(fat_target_g) if fat_target_g is not None else None
    goal.meal_distribution = meal_distribution or DEFAULT_MEAL_DISTRIBUTION
    goal.effective_from = effective_from
    goal.is_active = is_active
    goal.save()
    NutritionGoal.objects.filter(user=user, member_id=member_id).exclude(id=goal.id).update(is_active=False)
    return goal
