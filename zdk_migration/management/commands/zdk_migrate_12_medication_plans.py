from medical.models import MedicationPlan, MedicineBox

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_fetch_all
from zdk_migration.lib.transforms import medication_status_to_new, migration_extra, reminder_times_from_legacy, to_date


class Command(ZdkMigrateCommand):
    help = "Migrate aera_medication -> medical_medication_plan (+ medicine_box)"

    def run_migration(self) -> None:
        rows = old_fetch_all(
            """
            SELECT id, record_id, patient_id, batch_id, user_id, name, specification, dosage,
                   manufacturer, frequency, duration, instructions, reminder_enabled,
                   medication_times, start_date, end_date, status, notes, is_deleted,
                   created_at, updated_at
            FROM aera_medication
            ORDER BY id
            """
        )
        self.stdout.write(f"Found {len(rows)} medications")
        for row in rows:
            old_id = row["id"]
            skip, _ = self.resolve_mapped_row("medication", old_id, MedicationPlan)
            if skip:
                self.stats.skipped += 1
                continue
            member_id = self.id_map.get("patient", row.get("patient_id"))
            if not member_id:
                self.log_skip(f"medication patient not mapped id={row.get('patient_id')}")
                continue
            user_id = row.get("user_id")
            case_id = self.id_map.get("medical_record", row.get("record_id")) if row.get("record_id") else None
            prescription_id = self.id_map.get("prescription_batch", row.get("batch_id")) if row.get("batch_id") else None
            start_date = to_date(row.get("start_date"))
            if not start_date:
                self.log_skip(f"medication missing start_date old_id={old_id}")
                continue
            if self.dry_run:
                self.id_map.set("medication", old_id, old_id)
                self.stats.migrated += 1
                continue

            extra = migration_extra(
                "aera_medication",
                old_id,
                specification=row.get("specification") or "",
                manufacturer=row.get("manufacturer") or "",
                duration=row.get("duration") or "",
                notes=row.get("notes") or "",
            )

            def _create(row=row, old_id=old_id, member_id=member_id, user_id=user_id, case_id=case_id, prescription_id=prescription_id, start_date=start_date, extra=extra):
                box = MedicineBox.all_objects.create(
                    user_id=user_id,
                    member_id=member_id,
                    medicine_name=(row.get("name") or "medication")[:255],
                    strength=row.get("specification") or "",
                    notes="Migrated from ZhaodkDream",
                    extra=migration_extra("aera_medication_box", old_id),
                )
                plan = MedicationPlan.all_objects.create(
                    user_id=user_id,
                    member_id=member_id,
                    medical_case_id=case_id,
                    medicine_box_id=box.id,
                    prescription_id=prescription_id,
                    drug_name=(row.get("name") or "medication")[:255],
                    dose_per_time=(row.get("dosage") or "-")[:64],
                    dose_unit="片",
                    frequency_type=MedicationPlan.FrequencyType.DAILY,
                    frequency_text=(row.get("frequency") or "daily")[:255],
                    reminder_times=reminder_times_from_legacy(row.get("medication_times")),
                    start_date=start_date,
                    end_date=to_date(row.get("end_date")),
                    instructions=row.get("instructions") or "",
                    reminder_enabled=bool(row.get("reminder_enabled")),
                    status=medication_status_to_new(row.get("status")),
                    is_deleted=bool(row.get("is_deleted")),
                    extra=extra,
                )
                MedicationPlan.all_objects.filter(pk=plan.pk).update(
                    created_at=row.get("created_at") or plan.created_at,
                    updated_at=row.get("updated_at") or plan.updated_at,
                )
                return plan.id, box.id

            try:
                new_id, new_box_id = _create()
                self.id_map.set("medication", old_id, new_id)
                self.id_map.set("medicine_box", old_id, new_box_id)
                self.stats.migrated += 1
            except Exception as exc:
                self.log_fail(f"medication:{old_id}", exc)
