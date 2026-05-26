from medical.models import FollowUp, MedicalCase, Surgery, Symptom, Visit

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_select
from zdk_migration.lib.transforms import migration_extra, parse_duration, visit_type_to_new


class Command(ZdkMigrateCommand):
    help = "Migrate symptoms, visits, surgeries, follow-ups"

    def run_migration(self) -> None:
        self._migrate_symptoms()
        self._migrate_visits()
        self._migrate_surgeries()
        self._migrate_followups()

    def _case_context(self, record_id: int):
        case_id = self.id_map.get("medical_record", record_id)
        if not case_id:
            return None, None, None
        case = MedicalCase.all_objects.filter(pk=case_id).first()
        if not case:
            return None, None, None
        return case_id, case.member_id, case.user_id

    def _migrate_symptoms(self) -> None:
        rows = old_select(
            "aera_symptom",
            ["id", "record_id", "user_id", "description", "severity", "onset_date", "duration", "is_deleted", "created_at"],
            order_by="id",
        )
        self.stdout.write(f"Found {len(rows)} symptoms")
        for row in rows:
            case_id, member_id, user_id = self._case_context(row["record_id"])
            if not case_id:
                self.log_skip(f"symptom case missing record_id={row['record_id']}")
                continue
            dur_val, dur_unit, dur_text = parse_duration(row.get("duration"))
            extra = migration_extra("aera_symptom", row["id"])
            if dur_text and not dur_val:
                extra["duration_text"] = dur_text
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(row=row, case_id=case_id, member_id=member_id, user_id=user_id, extra=extra, dur_val=dur_val, dur_unit=dur_unit):
                obj = Symptom.all_objects.create(
                    user_id=user_id,
                    member_id=member_id,
                    medical_case_id=case_id,
                    name=(row.get("description") or "symptom")[:128],
                    severity=row.get("severity") or "",
                    started_at=row.get("onset_date"),
                    duration_value=dur_val,
                    duration_unit=dur_unit,
                    is_deleted=bool(row.get("is_deleted")),
                    extra=extra,
                )
                if row.get("created_at"):
                    Symptom.all_objects.filter(pk=obj.pk).update(created_at=row["created_at"])

            if self.run_safe(f"symptom:{row['id']}", _create):
                self.stats.migrated += 1

    def _migrate_visits(self) -> None:
        rows = old_select(
            "aera_visit",
            [
                "id", "record_id", "user_id", "date", "hospital", "department", "visit_type",
                "diagnosis", "treatment", "detail", "doctor", "is_deleted", "created_at",
            ],
            order_by="id",
        )
        self.stdout.write(f"Found {len(rows)} visits")
        for row in rows:
            case_id, member_id, user_id = self._case_context(row["record_id"])
            if not case_id:
                self.log_skip(f"visit case missing record_id={row['record_id']}")
                continue
            extra = migration_extra(
                "aera_visit",
                row["id"],
                hospital=row.get("hospital") or "",
                treatment=row.get("treatment") or "",
                detail=row.get("detail") or "",
                diagnosis=row.get("diagnosis") or "",
            )
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(row=row, case_id=case_id, member_id=member_id, user_id=user_id, extra=extra):
                notes_parts = [row.get("diagnosis") or "", row.get("treatment") or "", row.get("detail") or ""]
                Visit.all_objects.create(
                    user_id=user_id,
                    member_id=member_id,
                    medical_case_id=case_id,
                    visit_type=visit_type_to_new(row.get("visit_type")),
                    visited_at=row.get("date"),
                    department=row.get("department") or "",
                    doctor_name=row.get("doctor") or "",
                    source_system_id=f"zdk_visit_{row['id']}",
                    notes="\n".join(p for p in notes_parts if p).strip(),
                    is_deleted=bool(row.get("is_deleted")),
                    extra=extra,
                )

            if self.run_safe(f"visit:{row['id']}", _create):
                self.stats.migrated += 1

    def _migrate_surgeries(self) -> None:
        rows = old_select(
            "aera_surgery",
            [
                "id", "record_id", "user_id", "surgery_name", "date", "surgeon", "hospital",
                "anesthesia", "description", "outcome", "is_deleted", "created_at",
            ],
            order_by="id",
        )
        self.stdout.write(f"Found {len(rows)} surgeries")
        for row in rows:
            case_id, member_id, user_id = self._case_context(row["record_id"])
            if not case_id:
                self.log_skip(f"surgery case missing record_id={row['record_id']}")
                continue
            extra = migration_extra(
                "aera_surgery",
                row["id"],
                hospital=row.get("hospital") or "",
                outcome=row.get("outcome") or "",
            )
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(row=row, case_id=case_id, member_id=member_id, user_id=user_id, extra=extra):
                Surgery.all_objects.create(
                    user_id=user_id,
                    member_id=member_id,
                    medical_case_id=case_id,
                    procedure_name=row.get("surgery_name") or "",
                    performed_at=row.get("date"),
                    surgeon=row.get("surgeon") or "",
                    anesthesia_type=row.get("anesthesia") or "",
                    notes=row.get("description") or "",
                    source_system_id=f"zdk_surgery_{row['id']}",
                    is_deleted=bool(row.get("is_deleted")),
                    extra=extra,
                )

            if self.run_safe(f"surgery:{row['id']}", _create):
                self.stats.migrated += 1

    def _migrate_followups(self) -> None:
        rows = old_select(
            "aera_follow_up",
            ["id", "record_id", "user_id", "follow_up_date", "method", "content", "next_plan", "is_deleted", "created_at"],
            order_by="id",
        )
        self.stdout.write(f"Found {len(rows)} follow-ups")
        for row in rows:
            case_id, member_id, user_id = self._case_context(row["record_id"])
            if not case_id:
                self.log_skip(f"followup case missing record_id={row['record_id']}")
                continue
            if self.dry_run:
                self.stats.migrated += 1
                continue

            def _create(row=row, case_id=case_id, member_id=member_id, user_id=user_id):
                FollowUp.all_objects.create(
                    user_id=user_id,
                    member_id=member_id,
                    medical_case_id=case_id,
                    planned_at=row.get("follow_up_date"),
                    completed_at=row.get("follow_up_date"),
                    status="completed",
                    method=row.get("method") or "",
                    outcome=row.get("content") or "",
                    next_action=row.get("next_plan") or "",
                    is_deleted=bool(row.get("is_deleted")),
                    extra=migration_extra("aera_follow_up", row["id"]),
                )

            if self.run_safe(f"followup:{row['id']}", _create):
                self.stats.migrated += 1
