"""系统预置食物与标准营养种子数据。"""

from __future__ import annotations

from decimal import Decimal

from nutrition.constants import NUTRITION_BUSINESS_TYPE_FOOD_ITEM
from nutrition.models import NutritionFoodItem, NutritionIntake

SYSTEM_FOOD_SEED_KEY = "system_food_seed_key"

SYSTEM_FOODS = [
    {
        "seed_key": "coffee",
        "name": "Coffee",
        "localized_name": "咖啡",
        "category": "饮品",
        "serving_quantity": Decimal("1"),
        "serving_unit": "cup",
        "serving_description": "1杯（237毫升）",
        "weight_grams": Decimal("237"),
        "barcode": "",
        "sort_weight": 100,
        "intakes": {
            "energy_kcal": ("2", "kcal"),
            "protein_g": ("0.3", "g"),
            "carbohydrate_g": ("0", "g"),
            "fat_g": ("0", "g"),
        },
    },
    {
        "seed_key": "banana",
        "name": "Banana",
        "localized_name": "香蕉",
        "category": "水果",
        "serving_quantity": Decimal("1"),
        "serving_unit": "piece",
        "serving_description": "1整个，普通 (150克)",
        "weight_grams": Decimal("150"),
        "barcode": "",
        "sort_weight": 90,
        "intakes": {
            "energy_kcal": ("134", "kcal"),
            "protein_g": ("1.6", "g"),
            "carbohydrate_g": ("34.3", "g"),
            "fat_g": ("0.5", "g"),
        },
    },
    {
        "seed_key": "scrambled_eggs",
        "name": "Scrambled Eggs",
        "localized_name": "炒鸡蛋",
        "category": "肉蛋奶",
        "serving_quantity": Decimal("1"),
        "serving_unit": "egg",
        "serving_description": "1个鸡蛋 (47克)",
        "weight_grams": Decimal("47"),
        "barcode": "",
        "sort_weight": 80,
        "intakes": {
            "energy_kcal": ("100", "kcal"),
            "protein_g": ("6.8", "g"),
            "carbohydrate_g": ("1.2", "g"),
            "fat_g": ("7.5", "g"),
        },
    },
    {
        "seed_key": "apple",
        "name": "Apple",
        "localized_name": "苹果",
        "category": "水果",
        "serving_quantity": Decimal("1"),
        "serving_unit": "piece",
        "serving_description": "1个中等大小 (182克)",
        "weight_grams": Decimal("182"),
        "barcode": "6926104997449",
        "sort_weight": 70,
        "intakes": {
            "energy_kcal": ("95", "kcal"),
            "protein_g": ("0.5", "g"),
            "carbohydrate_g": ("25.1", "g"),
            "fat_g": ("0.3", "g"),
        },
    },
    {
        "seed_key": "strawberries",
        "name": "Strawberries",
        "localized_name": "草莓",
        "category": "水果",
        "serving_quantity": Decimal("1"),
        "serving_unit": "cup",
        "serving_description": "1杯 (152克)",
        "weight_grams": Decimal("152"),
        "barcode": "",
        "sort_weight": 60,
        "intakes": {
            "energy_kcal": ("49", "kcal"),
            "protein_g": ("1.0", "g"),
            "carbohydrate_g": ("11.7", "g"),
            "fat_g": ("0.5", "g"),
        },
    },
]


def _seed_extra(seed_key: str) -> dict:
    return {SYSTEM_FOOD_SEED_KEY: seed_key}


def seed_system_foods(apps=None, schema_editor=None):
    for item in SYSTEM_FOODS:
        extra = _seed_extra(item["seed_key"])
        food = NutritionFoodItem.objects.filter(
            user__isnull=True,
            extra__contains={SYSTEM_FOOD_SEED_KEY: item["seed_key"]},
        ).first()
        if food is None:
            food = NutritionFoodItem.objects.create(
                user=None,
                name=item["name"],
                localized_name=item["localized_name"],
                category=item["category"],
                serving_quantity=item["serving_quantity"],
                serving_unit=item["serving_unit"],
                serving_description=item["serving_description"],
                weight_grams=item["weight_grams"],
                barcode=item["barcode"],
                source="system",
                is_verified=True,
                is_active=True,
                sort_weight=item["sort_weight"],
                extra=extra,
            )
        else:
            NutritionFoodItem.objects.filter(pk=food.pk).update(
                name=item["name"],
                localized_name=item["localized_name"],
                category=item["category"],
                serving_quantity=item["serving_quantity"],
                serving_unit=item["serving_unit"],
                serving_description=item["serving_description"],
                weight_grams=item["weight_grams"],
                barcode=item["barcode"],
                source="system",
                is_verified=True,
                is_active=True,
                sort_weight=item["sort_weight"],
                extra=extra,
            )
            food.refresh_from_db()

        for nutrient_type, (value, unit) in item["intakes"].items():
            NutritionIntake.objects.update_or_create(
                business_type=NUTRITION_BUSINESS_TYPE_FOOD_ITEM,
                business_id=food.id,
                nutrient_type=nutrient_type,
                defaults={
                    "value": Decimal(value),
                    "unit": unit,
                    "source": "system",
                },
            )


def unseed_system_foods(apps=None, schema_editor=None):
    for item in SYSTEM_FOODS:
        matched = NutritionFoodItem.objects.filter(
            user__isnull=True,
            extra__contains={SYSTEM_FOOD_SEED_KEY: item["seed_key"]},
        )
        food_ids = list(matched.values_list("id", flat=True))
        if not food_ids:
            continue
        NutritionIntake.objects.filter(
            business_type=NUTRITION_BUSINESS_TYPE_FOOD_ITEM,
            business_id__in=food_ids,
        ).delete()
        matched.delete()
