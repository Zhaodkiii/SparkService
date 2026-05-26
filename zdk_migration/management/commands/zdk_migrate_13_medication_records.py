from datetime import datetime, time as dt_time

from medical.models import MedicationPlan, MedicationRecord

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_fetch_all
from zdk_migration.lib.transforms import migration_extra, taken_action_to_record_status


class Command(ZdkMigrateCommand):
    help = "Migrate aera_medication_taken_record -> medical_medication_record"

    def run_migration(self) -> None:
        rows = old_fetch_all(
            """
            SELECT id, medication_id, user_id, taken_at, time_string, action_type, notes, created_at
            FROM aera_medication_taken_record
            ORDER BY id
            """
        )
        self.stdout.write(f"Found {len(rows)} medication taken records")
        for row in rows:
            plan_id = self.id_map.get("medication", row.get("medication_id"))
            if not plan_id:
                self.log_skip(f"taken_record plan not mapped medication_id={row.get('medication_id')}")
                continue
            plan = MedicationPlan.all_objects.filter(pk=plan_id).first()
            if not plan:
                self.log_skip(f"plan missing id={plan_id}")
                continue
            taken_at = row.get("taken_at")
            scheduled_at = self._scheduled_at(taken_at, row.get("time_string"))
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(row=row, plan=plan, plan_id=plan_id, taken_at=taken_at, scheduled_at=scheduled_at):
                MedicationRecord.all_objects.create(
                    user_id=plan.user_id,
                    member_id=plan.member_id,
                    plan_id=plan_id,
                    scheduled_at=scheduled_at,
                    taken_at=taken_at,
                    status=taken_action_to_record_status(row.get("action_type")),
                    planned_dose=plan.dose_per_time,
                    actual_dose=plan.dose_per_time if row.get("action_type") == "taken" else "",
                    dose_sequence=1,
                    notes=row.get("notes") or "",
                    extra=migration_extra("aera_medication_taken_record", row["id"], time_string=row.get("time_string") or ""),
                )

            self.run_safe(f"taken_record:{row['id']}", _create)
            self.stats.migrated += 1

    @staticmethod
    def _scheduled_at(taken_at, time_string: str | None):
        if taken_at and time_string and ":" in time_string:
            try:
                hour, minute = [int(x) for x in time_string.split(":", 1)]
                base = taken_at if isinstance(taken_at, datetime) else datetime.fromisoformat(str(taken_at))
                return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except (ValueError, TypeError):
                pass
        return taken_at or datetime.now()
