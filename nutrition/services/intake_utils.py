"""营养摄入聚合、计算与序列化工具。"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.db.models import QuerySet, Sum

from nutrition.constants import (
    NUTRITION_BUSINESS_TYPE_FOOD_ITEM,
    NUTRITION_BUSINESS_TYPE_MEAL_RECORD,
)
from nutrition.models import NutritionIntake

MACRO_NUTRIENTS = (
    NutritionIntake.NutrientType.ENERGY,
    NutritionIntake.NutrientType.PROTEIN,
    NutritionIntake.NutrientType.CARBOHYDRATE,
    NutritionIntake.NutrientType.FAT,
)

DEFAULT_UNITS = {
    NutritionIntake.NutrientType.ENERGY: "kcal",
    NutritionIntake.NutrientType.PROTEIN: "g",
    NutritionIntake.NutrientType.CARBOHYDRATE: "g",
    NutritionIntake.NutrientType.FAT: "g",
}


def quantize(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def empty_macro_dict() -> dict[str, float]:
    return {item.value: 0.0 for item in MACRO_NUTRIENTS}


def macro_dict_from_decimals(values: dict[str, Decimal]) -> dict[str, float]:
    return {key: float(quantize(val)) for key, val in values.items()}


def serialize_macro_overview(values: dict[str, float]) -> dict[str, float]:
    return {
        "energy_kcal": values.get(NutritionIntake.NutrientType.ENERGY, 0.0),
        "protein_g": values.get(NutritionIntake.NutrientType.PROTEIN, 0.0),
        "carbohydrate_g": values.get(NutritionIntake.NutrientType.CARBOHYDRATE, 0.0),
        "fat_g": values.get(NutritionIntake.NutrientType.FAT, 0.0),
    }


def aggregate_intakes_queryset(queryset: QuerySet[NutritionIntake]) -> dict[str, float]:
    totals = empty_macro_dict()
    rows = queryset.filter(nutrient_type__in=[item.value for item in MACRO_NUTRIENTS]).values("nutrient_type").annotate(total=Sum("value"))
    for row in rows:
        totals[row["nutrient_type"]] = float(quantize(row["total"] or 0))
    return totals


def aggregate_business_intakes(business_type: str, business_ids: list[int]) -> dict[str, float]:
    if not business_ids:
        return empty_macro_dict()
    queryset = NutritionIntake.objects.filter(business_type=business_type, business_id__in=business_ids)
    return aggregate_intakes_queryset(queryset)


def get_food_standard_intakes(food_item_id: int) -> dict[str, NutritionIntake]:
    rows = NutritionIntake.objects.filter(
        business_type=NUTRITION_BUSINESS_TYPE_FOOD_ITEM,
        business_id=food_item_id,
        nutrient_type__in=[item.value for item in MACRO_NUTRIENTS],
    )
    return {row.nutrient_type: row for row in rows}


def scaled_food_macros(food_item_id: int, serving_ratio: Decimal) -> dict[str, tuple[Decimal, str]]:
    totals: dict[str, tuple[Decimal, str]] = {}
    for nutrient_type, row in get_food_standard_intakes(food_item_id).items():
        totals[nutrient_type] = (quantize(row.value * serving_ratio), row.unit)
    for nutrient_type in [item.value for item in MACRO_NUTRIENTS]:
        if nutrient_type not in totals:
            totals[nutrient_type] = (Decimal("0"), DEFAULT_UNITS.get(nutrient_type, "g"))
    return totals


def merge_macro_totals(*parts: dict[str, tuple[Decimal, str]]) -> dict[str, tuple[Decimal, str]]:
    merged: dict[str, tuple[Decimal, str]] = {}
    for nutrient_type in [item.value for item in MACRO_NUTRIENTS]:
        total = Decimal("0")
        unit = DEFAULT_UNITS.get(nutrient_type, "g")
        for part in parts:
            if nutrient_type in part:
                total += part[nutrient_type][0]
                unit = part[nutrient_type][1]
        merged[nutrient_type] = (quantize(total), unit)
    return merged


def sync_meal_record_intakes(meal_record_id: int, totals: dict[str, tuple[Decimal, str]], *, source: str = "food_item") -> list[NutritionIntake]:
    saved: list[NutritionIntake] = []
    for nutrient_type, (value, unit) in totals.items():
        intake, _ = NutritionIntake.objects.update_or_create(
            business_type=NUTRITION_BUSINESS_TYPE_MEAL_RECORD,
            business_id=meal_record_id,
            nutrient_type=nutrient_type,
            defaults={"value": value, "unit": unit, "source": source},
        )
        saved.append(intake)
    return saved


def apply_manual_intakes(meal_record_id: int, manual_intakes: list[dict[str, Any]]) -> list[NutritionIntake]:
    saved: list[NutritionIntake] = []
    for item in manual_intakes:
        nutrient_type = item["nutrient_type"]
        intake, _ = NutritionIntake.objects.update_or_create(
            business_type=NUTRITION_BUSINESS_TYPE_MEAL_RECORD,
            business_id=meal_record_id,
            nutrient_type=nutrient_type,
            defaults={
                "value": quantize(item["value"]),
                "unit": item.get("unit") or DEFAULT_UNITS.get(nutrient_type, "g"),
                "source": item.get("source") or "manual",
            },
        )
        saved.append(intake)
    return saved


def serialize_intake(intake: NutritionIntake) -> dict[str, Any]:
    return {
        "id": intake.id,
        "business_type": intake.business_type,
        "business_id": intake.business_id,
        "nutrient_type": intake.nutrient_type,
        "value": float(intake.value),
        "unit": intake.unit,
        "source": intake.source,
        "apple_health_id": intake.apple_health_id or "",
    }


def serialize_intakes_for_business(business_type: str, business_id: int) -> list[dict[str, Any]]:
    rows = NutritionIntake.objects.filter(business_type=business_type, business_id=business_id).order_by("id")
    return [serialize_intake(row) for row in rows]


def create_standard_intakes(business_type: str, business_id: int, intakes: list[dict[str, Any]], *, source: str = "system") -> None:
    for item in intakes:
        nutrient_type = item["nutrient_type"]
        NutritionIntake.objects.update_or_create(
            business_type=business_type,
            business_id=business_id,
            nutrient_type=nutrient_type,
            defaults={
                "value": quantize(item["value"]),
                "unit": item.get("unit") or DEFAULT_UNITS.get(nutrient_type, "g"),
                "source": source,
            },
        )


def overview_for_business_ids(business_type: str, business_ids: list[int]) -> dict[str, float]:
    return serialize_macro_overview(aggregate_business_intakes(business_type, business_ids))
