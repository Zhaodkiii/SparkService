"""看板聚合。"""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.db.models import Prefetch, Sum

from nutrition.constants import (
    NUTRITION_BUSINESS_TYPE_APPLE_HEALTH_INTAKE_IMPORT,
    NUTRITION_BUSINESS_TYPE_MEAL_RECORD,
)
from nutrition.models import NutritionAppleHealthIntakeImport, NutritionEnergyBurnRecord, NutritionIntake, NutritionMealFood, NutritionMealRecord
from nutrition.services.goal_service import resolve_daily_goal, resolve_meal_macro_targets
from nutrition.services.intake_utils import aggregate_business_intakes, empty_macro_dict, quantize, serialize_macro_overview

MEAL_TYPES = (
    NutritionMealRecord.MealType.BREAKFAST,
    NutritionMealRecord.MealType.LUNCH,
    NutritionMealRecord.MealType.DINNER,
    NutritionMealRecord.MealType.SNACK,
)


def build_dashboard(user: User, member_id: int, local_day: date) -> dict:
    daily_goal = resolve_daily_goal(user, member_id)
    meal_targets = resolve_meal_macro_targets(user, member_id)

    meal_records = list(
        NutritionMealRecord.objects.filter(user=user, member_id=member_id, local_day=local_day)
        .prefetch_related(
            Prefetch("meal_foods", queryset=NutritionMealFood.objects.select_related("food_item").order_by("display_order", "id"))
        )
        .order_by("meal_type", "consumed_at", "id")
    )
    meal_record_ids = [item.id for item in meal_records]
    server_macros = aggregate_business_intakes(NUTRITION_BUSINESS_TYPE_MEAL_RECORD, meal_record_ids)

    import_ids = list(
        NutritionAppleHealthIntakeImport.objects.filter(user=user, member_id=member_id, local_day=local_day).values_list("id", flat=True)
    )
    external_macros = aggregate_business_intakes(NUTRITION_BUSINESS_TYPE_APPLE_HEALTH_INTAKE_IMPORT, import_ids)

    burned_total = (
        NutritionEnergyBurnRecord.objects.filter(user=user, member_id=member_id, local_day=local_day)
        .aggregate(total=Sum("energy_kcal"))
        .get("total")
    ) or 0

    meals = []
    records_by_type: dict[str, list[NutritionMealRecord]] = {item.value: [] for item in MEAL_TYPES}
    for record in meal_records:
        records_by_type[record.meal_type].append(record)

    for meal_type in MEAL_TYPES:
        type_records = records_by_type[meal_type.value]
        type_ids = [item.id for item in type_records]
        type_macros = aggregate_business_intakes(NUTRITION_BUSINESS_TYPE_MEAL_RECORD, type_ids) if type_ids else empty_macro_dict()
        targets = meal_targets[meal_type.value]
        food_names: list[str] = []
        for record in type_records:
            for meal_food in record.meal_foods.all():
                food = meal_food.food_item
                food_names.append(food.localized_name or food.name)
        meals.append(
            {
                "meal_type": meal_type.value,
                "energy_kcal": type_macros["energy_kcal"],
                "target_energy_kcal": targets["target_energy_kcal"],
                "protein_g": type_macros["protein_g"],
                "target_protein_g": targets["target_protein_g"],
                "carbohydrate_g": type_macros["carbohydrate_g"],
                "target_carbohydrate_g": targets["target_carbohydrate_g"],
                "fat_g": type_macros["fat_g"],
                "target_fat_g": targets["target_fat_g"],
                "food_summary": ", ".join(food_names[:5]),
                "record_count": len(type_records),
            }
        )

    return {
        "member_id": member_id,
        "date": local_day.isoformat(),
        "goal": serialize_macro_overview({key: float(value) for key, value in daily_goal.items()}),
        "server_intake": serialize_macro_overview(server_macros),
        "apple_health_external_intake": serialize_macro_overview(external_macros),
        "apple_health_burned": {
            "energy_kcal": float(quantize(burned_total)),
            "source": "server_records",
        },
        "meals": meals,
    }
