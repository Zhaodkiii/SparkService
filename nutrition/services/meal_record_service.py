"""饮食记录查询与写入。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from file_manager.business_relations import bind_files_to_business, files_for_business
from file_manager.serializers import ManagedFileAttachmentOutSerializer
from nutrition.constants import NUTRITION_BUSINESS_TYPE_MEAL_RECORD
from nutrition.models import NutritionFoodItem, NutritionIntake, NutritionMealFood, NutritionMealRecord, NutritionRecipe, NutritionRecipeFood
from nutrition.services.goal_service import resolve_meal_macro_targets
from nutrition.services.intake_utils import (
    apply_manual_intakes,
    aggregate_business_intakes,
    merge_macro_totals,
    scaled_food_macros,
    serialize_intake,
    serialize_intakes_for_business,
    serialize_macro_overview,
    sync_meal_record_intakes,
)


def _serialize_food_item(food: NutritionFoodItem) -> dict[str, Any]:
    return {
        "id": food.id,
        "name": food.name,
        "localized_name": food.localized_name,
        "brand_name": food.brand_name,
        "barcode": food.barcode,
        "serving_description": food.serving_description,
        "is_verified": food.is_verified,
    }


def serialize_meal_food(meal_food: NutritionMealFood) -> dict[str, Any]:
    return {
        "id": meal_food.id,
        "food_item": _serialize_food_item(meal_food.food_item),
        "serving_ratio": float(meal_food.serving_ratio),
        "serving_description": meal_food.serving_description,
        "display_order": meal_food.display_order,
    }


def serialize_meal_record(record: NutritionMealRecord, user: User) -> dict[str, Any]:
    meal_foods = [serialize_meal_food(item) for item in record.meal_foods.select_related("food_item").order_by("display_order", "id")]
    attachments_qs = files_for_business(user, "nutrition_meal_record", record.id)
    attachments = ManagedFileAttachmentOutSerializer(attachments_qs, many=True, context={"request": None}).data
    intakes = serialize_intakes_for_business(NUTRITION_BUSINESS_TYPE_MEAL_RECORD, record.id)
    has_apple_health = any(item.get("apple_health_id") for item in intakes)
    return {
        "id": record.id,
        "meal_type": record.meal_type,
        "title": record.title,
        "source": record.source,
        "consumed_at": record.consumed_at.isoformat(),
        "meal_foods": meal_foods,
        "intakes": intakes,
        "attachments": attachments,
        "has_apple_health_id": has_apple_health,
    }


def list_meal_records(user: User, member_id: int, local_day: date, meal_type: str | None = None) -> dict[str, Any]:
    queryset = (
        NutritionMealRecord.objects.filter(user=user, member_id=member_id, local_day=local_day)
        .prefetch_related(
            Prefetch("meal_foods", queryset=NutritionMealFood.objects.select_related("food_item").order_by("display_order", "id"))
        )
        .order_by("consumed_at", "id")
    )
    if meal_type:
        queryset = queryset.filter(meal_type=meal_type)

    records = list(queryset)
    record_ids = [item.id for item in records]
    overview_macros = aggregate_business_intakes(NUTRITION_BUSINESS_TYPE_MEAL_RECORD, record_ids)
    overview = serialize_macro_overview(overview_macros)

    meal_targets = resolve_meal_macro_targets(user, member_id)
    if meal_type and meal_type in meal_targets:
        targets = meal_targets[meal_type]
    else:
        from nutrition.services.goal_service import resolve_daily_goal

        daily = resolve_daily_goal(user, member_id)
        targets = {
            "target_energy_kcal": float(daily["energy_kcal"]),
            "target_protein_g": float(daily["protein_g"]),
            "target_carbohydrate_g": float(daily["carbohydrate_g"]),
            "target_fat_g": float(daily["fat_g"]),
        }

    macro_progress = {
        "energy_kcal": overview["energy_kcal"],
        "target_energy_kcal": targets["target_energy_kcal"],
        "protein_g": overview["protein_g"],
        "target_protein_g": targets["target_protein_g"],
        "carbohydrate_g": overview["carbohydrate_g"],
        "target_carbohydrate_g": targets["target_carbohydrate_g"],
        "fat_g": overview["fat_g"],
        "target_fat_g": targets["target_fat_g"],
    }

    return {
        "member_id": member_id,
        "date": local_day.isoformat(),
        "meal_type": meal_type or "",
        "overview": overview,
        "macro_progress": macro_progress,
        "records": [serialize_meal_record(record, user) for record in records],
    }


def list_meal_records_history(user: User, member_id: int, date_from: date, date_to: date) -> dict[str, Any]:
    queryset = (
        NutritionMealRecord.objects.filter(
            user=user,
            member_id=member_id,
            local_day__gte=date_from,
            local_day__lte=date_to,
            is_deleted=False,
        )
        .prefetch_related(
            Prefetch("meal_foods", queryset=NutritionMealFood.objects.select_related("food_item").order_by("display_order", "id"))
        )
        .order_by("-local_day", "-consumed_at", "-id")
    )
    records = list(queryset)
    return {
        "member_id": member_id,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "records": [serialize_meal_record(record, user) for record in records],
    }


def _derive_local_day(consumed_at: datetime) -> date:
    if timezone.is_aware(consumed_at):
        return timezone.localtime(consumed_at).date()
    return consumed_at.date()


def _collect_macros_from_payload(meal_foods: list[dict[str, Any]], recipes: list[dict[str, Any]]) -> dict[str, tuple[Decimal, str]]:
    parts: list[dict[str, tuple[Decimal, str]]] = []
    for item in meal_foods:
        ratio = Decimal(str(item.get("serving_ratio", 1)))
        parts.append(scaled_food_macros(item["food_item_id"], ratio))
    for recipe_item in recipes:
        recipe_ratio = Decimal(str(recipe_item.get("serving_ratio", 1)))
        recipe = NutritionRecipe.objects.filter(id=recipe_item["recipe_id"], is_active=True).first()
        if recipe is None:
            continue
        recipe_foods = NutritionRecipeFood.objects.filter(recipe=recipe).select_related("food_item")
        for recipe_food in recipe_foods:
            combined_ratio = recipe_ratio * recipe_food.serving_ratio
            parts.append(scaled_food_macros(recipe_food.food_item_id, combined_ratio))
    return merge_macro_totals(*parts) if parts else merge_macro_totals()


@transaction.atomic
def create_meal_record(user: User, payload: dict[str, Any]) -> dict[str, Any]:
    consumed_at = payload["consumed_at"]
    local_day = payload.get("local_day") or _derive_local_day(consumed_at)
    extra = {}
    if payload.get("recognition_id"):
        extra["recognition_id"] = payload["recognition_id"]

    record = NutritionMealRecord.objects.create(
        user=user,
        member_id=payload["member_id"],
        meal_type=payload["meal_type"],
        consumed_at=consumed_at,
        local_day=local_day,
        title=payload.get("title") or "",
        source=payload.get("source") or NutritionMealRecord.Source.MANUAL,
        source_text=payload.get("source_text") or "",
        is_ai_estimated=payload.get("source") in {NutritionMealRecord.Source.PHOTO_AI, NutritionMealRecord.Source.TEXT_AI, NutritionMealRecord.Source.CHAT_AI},
        extra=extra,
    )

    display_order = 0
    for item in payload.get("meal_foods") or []:
        food = NutritionFoodItem.objects.filter(id=item["food_item_id"], is_active=True).first()
        if food is None:
            continue
        NutritionMealFood.objects.create(
            meal_record=record,
            food_item=food,
            serving_ratio=Decimal(str(item.get("serving_ratio", 1))),
            serving_quantity=item.get("serving_quantity"),
            serving_unit=item.get("serving_unit") or "",
            serving_description=item.get("serving_description") or food.serving_description,
            display_order=display_order,
        )
        display_order += 1

    for recipe_item in payload.get("recipes") or []:
        recipe_ratio = Decimal(str(recipe_item.get("serving_ratio", 1)))
        recipe = NutritionRecipe.objects.filter(id=recipe_item["recipe_id"], is_active=True).first()
        if recipe is None:
            continue
        recipe_foods = NutritionRecipeFood.objects.filter(recipe=recipe).select_related("food_item").order_by("display_order", "id")
        for recipe_food in recipe_foods:
            combined_ratio = recipe_ratio * recipe_food.serving_ratio
            NutritionMealFood.objects.create(
                meal_record=record,
                food_item=recipe_food.food_item,
                serving_ratio=combined_ratio,
                serving_quantity=recipe_item.get("serving_quantity"),
                serving_unit=recipe_item.get("serving_unit") or recipe_food.serving_unit,
                serving_description=recipe_item.get("serving_description") or recipe_food.serving_description,
                display_order=display_order,
                extra={"source_recipe_id": recipe.id},
            )
            display_order += 1

    manual_intakes = payload.get("manual_intakes") or []
    if manual_intakes:
        apply_manual_intakes(record.id, manual_intakes)
    else:
        totals = _collect_macros_from_payload(payload.get("meal_foods") or [], payload.get("recipes") or [])
        sync_meal_record_intakes(record.id, totals, source=payload.get("source") or "food_item")

    file_ids = payload.get("file_ids") or []
    if file_ids:
        bind_files_to_business(user, "nutrition_meal_record", record.id, file_ids)

    record.refresh_from_db()
    return serialize_meal_record(record, user)


@transaction.atomic
def update_meal_record(user: User, record_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    record = NutritionMealRecord.objects.filter(id=record_id, user=user, is_deleted=False).first()
    if record is None:
        return None

    if "meal_type" in payload:
        record.meal_type = payload["meal_type"]
    if "title" in payload:
        record.title = payload["title"] or ""
    if "source" in payload:
        record.source = payload["source"]
    if "source_text" in payload:
        record.source_text = payload["source_text"] or ""
    if "consumed_at" in payload:
        record.consumed_at = payload["consumed_at"]
        record.local_day = payload.get("local_day") or _derive_local_day(record.consumed_at)
    record.user_edited = True
    record.save()

    if "meal_foods" in payload or "recipes" in payload:
        record.meal_foods.all().delete()
        create_payload = {
            "member_id": record.member_id,
            "meal_foods": payload.get("meal_foods") or [],
            "recipes": payload.get("recipes") or [],
            "manual_intakes": payload.get("manual_intakes") or [],
            "source": record.source,
        }
        display_order = 0
        for item in create_payload["meal_foods"]:
            food = NutritionFoodItem.objects.filter(id=item["food_item_id"], is_active=True).first()
            if food is None:
                continue
            NutritionMealFood.objects.create(
                meal_record=record,
                food_item=food,
                serving_ratio=Decimal(str(item.get("serving_ratio", 1))),
                serving_quantity=item.get("serving_quantity"),
                serving_unit=item.get("serving_unit") or "",
                serving_description=item.get("serving_description") or food.serving_description,
                display_order=display_order,
            )
            display_order += 1
        for recipe_item in create_payload["recipes"]:
            recipe_ratio = Decimal(str(recipe_item.get("serving_ratio", 1)))
            recipe = NutritionRecipe.objects.filter(id=recipe_item["recipe_id"], is_active=True).first()
            if recipe is None:
                continue
            recipe_foods = NutritionRecipeFood.objects.filter(recipe=recipe).select_related("food_item").order_by("display_order", "id")
            for recipe_food in recipe_foods:
                combined_ratio = recipe_ratio * recipe_food.serving_ratio
                NutritionMealFood.objects.create(
                    meal_record=record,
                    food_item=recipe_food.food_item,
                    serving_ratio=combined_ratio,
                    serving_quantity=recipe_item.get("serving_quantity"),
                    serving_unit=recipe_item.get("serving_unit") or recipe_food.serving_unit,
                    serving_description=recipe_item.get("serving_description") or recipe_food.serving_description,
                    display_order=display_order,
                    extra={"source_recipe_id": recipe.id},
                )
                display_order += 1

        if create_payload["manual_intakes"]:
            apply_manual_intakes(record.id, create_payload["manual_intakes"])
        else:
            totals = _collect_macros_from_payload(create_payload["meal_foods"], create_payload["recipes"])
            sync_meal_record_intakes(record.id, totals, source=record.source or "food_item")

    if "file_ids" in payload:
        bind_files_to_business(user, "nutrition_meal_record", record.id, payload.get("file_ids") or [])

    record.refresh_from_db()
    return serialize_meal_record(record, user)


def delete_meal_record(user: User, record_id: int) -> dict[str, Any] | None:
    record = NutritionMealRecord.objects.filter(id=record_id, user=user, is_deleted=False).first()
    if record is None:
        return None
    intakes = serialize_intakes_for_business(NUTRITION_BUSINESS_TYPE_MEAL_RECORD, record.id)
    has_apple_health = any(item.get("apple_health_id") for item in intakes)
    record.soft_delete()
    return {"id": record.id, "deleted": True, "has_apple_health_id": has_apple_health, "intake_ids": [item["id"] for item in intakes]}
