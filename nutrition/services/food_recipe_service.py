"""自定义食物与菜谱创建。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction

from nutrition.constants import NUTRITION_BUSINESS_TYPE_FOOD_ITEM, NUTRITION_BUSINESS_TYPE_RECIPE
from nutrition.models import NutritionFoodItem, NutritionRecipe, NutritionRecipeFood
from nutrition.services.intake_utils import create_standard_intakes, overview_for_business_ids, scaled_food_macros, serialize_intakes_for_business


def _serialize_food_item(food: NutritionFoodItem) -> dict[str, Any]:
    return {
        "id": food.id,
        "name": food.name,
        "localized_name": food.localized_name,
        "brand_name": food.brand_name,
        "barcode": food.barcode,
        "category": food.category,
        "serving_quantity": float(food.serving_quantity) if food.serving_quantity is not None else None,
        "serving_unit": food.serving_unit,
        "serving_description": food.serving_description,
        "weight_grams": float(food.weight_grams) if food.weight_grams is not None else None,
        "is_verified": food.is_verified,
    }


@transaction.atomic
def create_custom_food(user: User, payload: dict[str, Any]) -> dict[str, Any]:
    food = NutritionFoodItem.objects.create(
        user=user,
        name=payload["name"],
        localized_name=payload.get("localized_name") or payload["name"],
        brand_name=payload.get("brand_name") or "",
        barcode=payload.get("barcode") or "",
        category=payload.get("category") or "",
        serving_quantity=payload.get("serving_quantity"),
        serving_unit=payload.get("serving_unit") or "",
        serving_description=payload.get("serving_description") or "",
        weight_grams=payload.get("weight_grams"),
        source="user_custom",
        is_verified=False,
        is_active=True,
    )
    create_standard_intakes(NUTRITION_BUSINESS_TYPE_FOOD_ITEM, food.id, payload.get("intakes") or [], source="user_custom")
    return {
        "food_item": _serialize_food_item(food),
        "overview": overview_for_business_ids(NUTRITION_BUSINESS_TYPE_FOOD_ITEM, [food.id]),
        "intakes": serialize_intakes_for_business(NUTRITION_BUSINESS_TYPE_FOOD_ITEM, food.id),
    }


@transaction.atomic
def create_custom_recipe(user: User, payload: dict[str, Any]) -> dict[str, Any]:
    recipe = NutritionRecipe.objects.create(
        user=user,
        name=payload["name"],
        localized_name=payload.get("localized_name") or payload["name"],
        category=payload.get("category") or "",
        serving_quantity=payload.get("serving_quantity"),
        serving_unit=payload.get("serving_unit") or "",
        serving_description=payload.get("serving_description") or "",
        source="user_custom",
        is_active=True,
    )
    display_order = 0
    macro_parts = []
    for item in payload.get("foods") or []:
        food = NutritionFoodItem.objects.filter(id=item["food_item_id"], is_active=True).first()
        if food is None:
            continue
        ratio = Decimal(str(item.get("serving_ratio", 1)))
        NutritionRecipeFood.objects.create(
            recipe=recipe,
            food_item=food,
            serving_ratio=ratio,
            serving_quantity=item.get("serving_quantity"),
            serving_unit=item.get("serving_unit") or "",
            serving_description=item.get("serving_description") or food.serving_description,
            display_order=display_order,
        )
        macro_parts.append(scaled_food_macros(food.id, ratio))
        display_order += 1

    from nutrition.services.intake_utils import merge_macro_totals

    totals = merge_macro_totals(*macro_parts) if macro_parts else merge_macro_totals()
    intakes_payload = [{"nutrient_type": nutrient_type, "value": float(value), "unit": unit} for nutrient_type, (value, unit) in totals.items()]
    create_standard_intakes(NUTRITION_BUSINESS_TYPE_RECIPE, recipe.id, intakes_payload, source="user_custom")

    recipe_foods = list(
        NutritionRecipeFood.objects.filter(recipe=recipe).select_related("food_item").order_by("display_order", "id")
    )
    return {
        "recipe": {
            "id": recipe.id,
            "name": recipe.name,
            "localized_name": recipe.localized_name,
            "category": recipe.category,
            "serving_description": recipe.serving_description,
            "foods": [
                {
                    "id": row.id,
                    "food_item_id": row.food_item_id,
                    "serving_ratio": float(row.serving_ratio),
                    "serving_description": row.serving_description,
                    "display_order": row.display_order,
                }
                for row in recipe_foods
            ],
        },
        "overview": overview_for_business_ids(NUTRITION_BUSINESS_TYPE_RECIPE, [recipe.id]),
        "intakes": serialize_intakes_for_business(NUTRITION_BUSINESS_TYPE_RECIPE, recipe.id),
    }
