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


def _quantize(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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
        "energy_kcal": _quantize(goal.daily_energy_target_kcal or DEFAULT_DAILY_GOAL["energy_kcal"]),
        "protein_g": _quantize(goal.protein_target_g or DEFAULT_DAILY_GOAL["protein_g"]),
        "carbohydrate_g": _quantize(goal.carbohydrate_target_g or DEFAULT_DAILY_GOAL["carbohydrate_g"]),
        "fat_g": _quantize(goal.fat_target_g or DEFAULT_DAILY_GOAL["fat_g"]),
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
