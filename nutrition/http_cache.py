"""饮食营养 GET 接口的 ETag 指纹生成。"""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.db.models import Q

from nutrition.constants import (
    NUTRITION_BUSINESS_TYPE_APPLE_HEALTH_INTAKE_IMPORT,
    NUTRITION_BUSINESS_TYPE_MEAL_RECORD,
)
from nutrition.models import (
    NutritionAppleHealthIntakeImport,
    NutritionEnergyBurnRecord,
    NutritionIntake,
    NutritionMealRecord,
)
from nutrition.services.goal_service import get_active_goal


def _record_rows(queryset) -> list[tuple[int, str]]:
    return [(row[0], row[1].isoformat()) for row in queryset.order_by("id").values_list("id", "updated_at")]


def _intake_rows(*filters: Q) -> list[tuple[int, str]]:
    if not filters:
        return []
    condition = filters[0]
    for extra in filters[1:]:
        condition |= extra
    return [
        (row[0], row[1].isoformat())
        for row in NutritionIntake.objects.filter(condition).order_by("id").values_list("id", "updated_at")
    ]


def build_defaults_etag_payload(user: User, member_id: int) -> dict:
    goal = get_active_goal(user, member_id)
    if goal is None:
        return {"goal": None}
    return {"goal": [goal.id, goal.updated_at.isoformat()]}


def build_dashboard_etag_payload(user: User, member_id: int, local_day: date) -> dict:
    meal_qs = NutritionMealRecord.objects.filter(
        user=user,
        member_id=member_id,
        local_day=local_day,
        is_deleted=False,
    )
    import_qs = NutritionAppleHealthIntakeImport.objects.filter(
        user=user,
        member_id=member_id,
        local_day=local_day,
        is_deleted=False,
    )
    burn_qs = NutritionEnergyBurnRecord.objects.filter(
        user=user,
        member_id=member_id,
        local_day=local_day,
        is_deleted=False,
    )

    meal_rows = _record_rows(meal_qs)
    import_rows = _record_rows(import_qs)
    burn_rows = _record_rows(burn_qs)

    meal_ids = [row[0] for row in meal_rows]
    import_ids = [row[0] for row in import_rows]
    intake_filters: list[Q] = []
    if meal_ids:
        intake_filters.append(Q(business_type=NUTRITION_BUSINESS_TYPE_MEAL_RECORD, business_id__in=meal_ids))
    if import_ids:
        intake_filters.append(
            Q(business_type=NUTRITION_BUSINESS_TYPE_APPLE_HEALTH_INTAKE_IMPORT, business_id__in=import_ids)
        )

    goal = get_active_goal(user, member_id)
    goal_key = [goal.id, goal.updated_at.isoformat()] if goal else None
    return {
        "meals": meal_rows,
        "imports": import_rows,
        "burns": burn_rows,
        "intakes": _intake_rows(*intake_filters),
        "goal": goal_key,
    }


def build_meal_records_etag_payload(
    user: User,
    member_id: int,
    *,
    local_day: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    meal_type: str | None = None,
) -> dict:
    qs = NutritionMealRecord.objects.filter(user=user, member_id=member_id, is_deleted=False)
    if local_day is not None:
        qs = qs.filter(local_day=local_day)
    if date_from is not None and date_to is not None:
        qs = qs.filter(local_day__gte=date_from, local_day__lte=date_to)
    if meal_type:
        qs = qs.filter(meal_type=meal_type)

    meal_rows = _record_rows(qs)
    meal_ids = [row[0] for row in meal_rows]
    intake_rows = (
        _intake_rows(Q(business_type=NUTRITION_BUSINESS_TYPE_MEAL_RECORD, business_id__in=meal_ids))
        if meal_ids
        else []
    )
    return {"records": meal_rows, "intakes": intake_rows}


def build_energy_burn_etag_payload(user: User, member_id: int, local_day: date) -> dict:
    qs = NutritionEnergyBurnRecord.objects.filter(
        user=user,
        member_id=member_id,
        local_day=local_day,
        is_deleted=False,
    )
    return {"records": _record_rows(qs)}
