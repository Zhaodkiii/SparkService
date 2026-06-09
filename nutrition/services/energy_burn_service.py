"""能量消耗记录与 Apple 健康同步。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from nutrition.constants import (
    NUTRITION_BUSINESS_TYPE_APPLE_HEALTH_INTAKE_IMPORT,
    NUTRITION_BUSINESS_TYPE_MEAL_RECORD,
)
from nutrition.models import NutritionAppleHealthIntakeImport, NutritionEnergyBurnRecord, NutritionIntake, NutritionMealRecord
from nutrition.services.intake_utils import create_standard_intakes, serialize_intake
from nutrition.services.member_utils import is_self_primary_member


def _derive_local_day(value: datetime) -> date:
    if timezone.is_aware(value):
        return timezone.localtime(value).date()
    return value.date()


def serialize_energy_burn(record: NutritionEnergyBurnRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "member_id": record.member_id,
        "burned_at": record.burned_at.isoformat(),
        "local_day": record.local_day.isoformat(),
        "energy_kcal": float(record.energy_kcal),
        "activity_type": record.activity_type,
        "duration_seconds": record.duration_seconds,
        "source": record.source,
        "note": record.note,
        "apple_health_id": record.apple_health_id or "",
    }


def list_energy_burn_records(user: User, member_id: int, local_day: date) -> dict[str, Any]:
    records = NutritionEnergyBurnRecord.objects.filter(user=user, member_id=member_id, local_day=local_day).order_by("-burned_at", "-id")
    return {
        "member_id": member_id,
        "date": local_day.isoformat(),
        "records": [serialize_energy_burn(record) for record in records],
    }


@transaction.atomic
def create_energy_burn_record(user: User, payload: dict[str, Any]) -> dict[str, Any]:
    burned_at = payload["burned_at"]
    record = NutritionEnergyBurnRecord.objects.create(
        user=user,
        member_id=payload["member_id"],
        burned_at=burned_at,
        local_day=payload.get("local_day") or _derive_local_day(burned_at),
        energy_kcal=payload["energy_kcal"],
        activity_type=payload.get("activity_type") or "",
        duration_seconds=payload.get("duration_seconds"),
        source=payload.get("source") or NutritionEnergyBurnRecord.Source.MANUAL,
        note=payload.get("note") or "",
    )
    return serialize_energy_burn(record)


def update_energy_burn_record(user: User, record_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    record = NutritionEnergyBurnRecord.objects.filter(id=record_id, user=user, is_deleted=False).first()
    if record is None:
        return None
    if "burned_at" in payload:
        record.burned_at = payload["burned_at"]
        record.local_day = payload.get("local_day") or _derive_local_day(record.burned_at)
    if "energy_kcal" in payload:
        record.energy_kcal = payload["energy_kcal"]
    if "activity_type" in payload:
        record.activity_type = payload["activity_type"] or ""
    if "duration_seconds" in payload:
        record.duration_seconds = payload["duration_seconds"]
    if "source" in payload:
        record.source = payload["source"]
    if "note" in payload:
        record.note = payload["note"] or ""
    record.save()
    return serialize_energy_burn(record)


def delete_energy_burn_record(user: User, record_id: int) -> dict[str, Any] | None:
    record = NutritionEnergyBurnRecord.objects.filter(id=record_id, user=user, is_deleted=False).first()
    if record is None:
        return None
    has_apple_health = bool(record.apple_health_id)
    record.soft_delete()
    return {"id": record.id, "deleted": True, "has_apple_health_id": has_apple_health}


def write_intake_apple_health_id(user: User, intake_id: int, apple_health_id: str) -> dict[str, Any] | None:
    intake = NutritionIntake.objects.filter(id=intake_id, business_type=NUTRITION_BUSINESS_TYPE_MEAL_RECORD).first()
    if intake is None:
        return None
    meal_record = NutritionMealRecord.objects.filter(id=intake.business_id, user=user, is_deleted=False).first()
    if meal_record is None:
        return None
    if not is_self_primary_member(user, meal_record.member_id):
        return {"error": "not_self_member"}
    intake.apple_health_id = apple_health_id
    intake.save(update_fields=["apple_health_id", "updated_at"])
    return serialize_intake(intake)


def write_energy_burn_apple_health_id(user: User, record_id: int, apple_health_id: str) -> dict[str, Any] | None:
    record = NutritionEnergyBurnRecord.objects.filter(id=record_id, user=user, is_deleted=False).first()
    if record is None:
        return None
    if not is_self_primary_member(user, record.member_id):
        return {"error": "not_self_member"}
    record.apple_health_id = apple_health_id
    record.save(update_fields=["apple_health_id", "updated_at"])
    return serialize_energy_burn(record)


@transaction.atomic
def import_apple_health_intakes(user: User, member_id: int, samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not is_self_primary_member(user, member_id):
        return {"error": "not_self_member"}

    imported = []
    duplicates = []
    for sample in samples:
        apple_health_id = sample["apple_health_id"]
        existing = NutritionAppleHealthIntakeImport.objects.filter(member_id=member_id, apple_health_id=apple_health_id).first()
        if existing:
            duplicates.append({"apple_health_id": apple_health_id, "import_id": existing.id, "duplicate": True})
            continue
        occurred_at = sample["occurred_at"]
        import_row = NutritionAppleHealthIntakeImport.objects.create(
            user=user,
            member_id=member_id,
            occurred_at=occurred_at,
            local_day=_derive_local_day(occurred_at),
            source_bundle_id=sample.get("source_bundle_id") or "",
            source_name=sample.get("source_name") or "",
            apple_health_id=apple_health_id,
        )
        intakes = sample.get("intakes") or []
        create_standard_intakes(
            NUTRITION_BUSINESS_TYPE_APPLE_HEALTH_INTAKE_IMPORT,
            import_row.id,
            intakes,
            source="apple_health_import",
        )
        for intake_row in NutritionIntake.objects.filter(
            business_type=NUTRITION_BUSINESS_TYPE_APPLE_HEALTH_INTAKE_IMPORT,
            business_id=import_row.id,
        ):
            intake_row.apple_health_id = apple_health_id
            intake_row.save(update_fields=["apple_health_id", "updated_at"])
        imported.append({"apple_health_id": apple_health_id, "import_id": import_row.id})

    return {"imported": imported, "duplicates": duplicates}


@transaction.atomic
def import_apple_health_energy_burns(user: User, member_id: int, samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not is_self_primary_member(user, member_id):
        return {"error": "not_self_member"}

    imported = []
    duplicates = []
    for sample in samples:
        apple_health_id = sample["apple_health_id"]
        existing = NutritionEnergyBurnRecord.objects.filter(member_id=member_id, apple_health_id=apple_health_id, is_deleted=False).first()
        if existing:
            duplicates.append({"apple_health_id": apple_health_id, "record_id": existing.id, "duplicate": True})
            continue
        burned_at = sample["burned_at"]
        record = NutritionEnergyBurnRecord.objects.create(
            user=user,
            member_id=member_id,
            burned_at=burned_at,
            local_day=_derive_local_day(burned_at),
            energy_kcal=sample["energy_kcal"],
            activity_type=sample.get("activity_type") or "",
            source=NutritionEnergyBurnRecord.Source.APPLE_HEALTH_IMPORT,
            apple_health_id=apple_health_id,
        )
        imported.append({"apple_health_id": apple_health_id, "record_id": record.id})
    return {"imported": imported, "duplicates": duplicates}
