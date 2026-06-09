"""食物/菜谱搜索与收藏。"""

from __future__ import annotations

import re
from typing import Any

from django.contrib.auth.models import User
from django.db.models import Q

from nutrition.constants import (
    NUTRITION_BUSINESS_TYPE_FOOD_ITEM,
    NUTRITION_BUSINESS_TYPE_RECIPE,
    NUTRITION_ERROR_INVALID_BARCODE,
    NUTRITION_FAVORITE_TARGET_FOOD_ITEM,
    NUTRITION_FAVORITE_TARGET_RECIPE,
)
from nutrition.models import NutritionFoodFavorite, NutritionFoodItem, NutritionRecipe
from nutrition.services.intake_utils import overview_for_business_ids

BARCODE_PATTERN = re.compile(r"^\d{8,14}$")


def _favorite_map(user: User) -> dict[tuple[str, int], bool]:
    rows = NutritionFoodFavorite.objects.filter(user=user, is_deleted=False)
    return {(row.target_type, row.target_id): True for row in rows}


def _serialize_search_food(food: NutritionFoodItem, user: User, favorite_map: dict[tuple[str, int], bool], *, score: float = 1.0) -> dict[str, Any]:
    return {
        "id": f"food_{food.id}",
        "result_type": "food_item",
        "food_item": {
            "id": food.id,
            "name": food.name,
            "localized_name": food.localized_name,
            "brand_name": food.brand_name,
            "barcode": food.barcode,
            "serving_description": food.serving_description,
            "is_verified": food.is_verified,
        },
        "recipe": None,
        "is_favorite": favorite_map.get((NUTRITION_FAVORITE_TARGET_FOOD_ITEM, food.id), False),
        "is_created_by_me": food.user_id == user.id if food.user_id else False,
        "overview": overview_for_business_ids(NUTRITION_BUSINESS_TYPE_FOOD_ITEM, [food.id]),
        "score": score,
    }


def _serialize_search_recipe(recipe: NutritionRecipe, user: User, favorite_map: dict[tuple[str, int], bool], *, score: float = 1.0) -> dict[str, Any]:
    return {
        "id": f"recipe_{recipe.id}",
        "result_type": "recipe",
        "food_item": None,
        "recipe": {
            "id": recipe.id,
            "name": recipe.name,
            "localized_name": recipe.localized_name,
            "category": recipe.category,
            "serving_description": recipe.serving_description,
        },
        "is_favorite": favorite_map.get((NUTRITION_FAVORITE_TARGET_RECIPE, recipe.id), False),
        "is_created_by_me": recipe.user_id == user.id if recipe.user_id else False,
        "overview": overview_for_business_ids(NUTRITION_BUSINESS_TYPE_RECIPE, [recipe.id]),
        "score": score,
    }


def search_items(
    user: User,
    *,
    member_id: int,
    mode: str,
    query: str,
    result_type: str = "all",
    favorite_only: bool = False,
    created_by_me: bool = False,
) -> dict[str, Any]:
    _ = member_id
    favorite_map = _favorite_map(user)
    items: list[dict[str, Any]] = []

    if mode == "barcode":
        if query and not BARCODE_PATTERN.match(query):
            return {"error_code": NUTRITION_ERROR_INVALID_BARCODE, "msg": "invalid_barcode"}
        foods = NutritionFoodItem.objects.filter(is_active=True, barcode=query).order_by("-sort_weight", "id")
        items = [_serialize_search_food(food, user, favorite_map) for food in foods]
        return {"mode": mode, "query": query, "items": items}

    food_qs = NutritionFoodItem.objects.filter(is_active=True)
    recipe_qs = NutritionRecipe.objects.filter(is_active=True)
    if query:
        keyword = Q(name__icontains=query) | Q(localized_name__icontains=query) | Q(brand_name__icontains=query)
        food_qs = food_qs.filter(keyword)
        recipe_qs = recipe_qs.filter(Q(name__icontains=query) | Q(localized_name__icontains=query))
    else:
        food_qs = food_qs.filter(user__isnull=True)

    if created_by_me:
        food_qs = food_qs.filter(user=user)
        recipe_qs = recipe_qs.filter(user=user)

    if favorite_only:
        favorite_food_ids = [target_id for (target_type, target_id), active in favorite_map.items() if active and target_type == NUTRITION_FAVORITE_TARGET_FOOD_ITEM]
        favorite_recipe_ids = [target_id for (target_type, target_id), active in favorite_map.items() if active and target_type == NUTRITION_FAVORITE_TARGET_RECIPE]
        food_qs = food_qs.filter(id__in=favorite_food_ids)
        recipe_qs = recipe_qs.filter(id__in=favorite_recipe_ids)

    if result_type == "food":
        recipe_qs = NutritionRecipe.objects.none()
    elif result_type == "recipe":
        food_qs = NutritionFoodItem.objects.none()

    for food in food_qs.order_by("-sort_weight", "name", "id")[:50]:
        items.append(_serialize_search_food(food, user, favorite_map))
    for recipe in recipe_qs.order_by("-sort_weight", "name", "id")[:50]:
        items.append(_serialize_search_recipe(recipe, user, favorite_map))

    return {"mode": mode, "query": query, "items": items}


def add_favorite(user: User, target_type: str, target_id: int) -> dict[str, Any]:
    favorite, created = NutritionFoodFavorite.objects.get_or_create(
        user=user,
        target_type=target_type,
        target_id=target_id,
        defaults={"is_deleted": False},
    )
    if not created and favorite.is_deleted:
        favorite.is_deleted = False
        favorite.save(update_fields=["is_deleted", "updated_at"])
    return {"target_type": target_type, "target_id": target_id, "is_favorite": True}


def remove_favorite(user: User, target_type: str, target_id: int) -> dict[str, Any]:
    favorite = NutritionFoodFavorite.objects.filter(user=user, target_type=target_type, target_id=target_id, is_deleted=False).first()
    if favorite:
        favorite.is_deleted = True
        favorite.save(update_fields=["is_deleted", "updated_at"])
    return {"target_type": target_type, "target_id": target_id, "is_favorite": False}
