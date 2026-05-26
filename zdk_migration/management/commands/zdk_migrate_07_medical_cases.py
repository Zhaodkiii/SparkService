from django.contrib.auth import get_user_model

from medical.models import MedicalCase, Member

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_fetch_all
from zdk_migration.lib.transforms import migration_extra


class Command(ZdkMigrateCommand):
    help = "Migrate aera_medical_record -> medical_medicalcase"

    def run_migration(self) -> None:
        User = get_user_model()
        rows = old_fetch_all(
            """
            SELECT id, patient_id, chief_complaint, diagnosis, severity, visit_date,
                   status, notes, is_deleted, deleted_at, created_at, updated_at
            FROM aera_medical_record
            ORDER BY id
            """
        )
        self.stdout.write(f"Found {len(rows)} medical records")
        for row in rows:
            old_id = row["id"]
            skip, _ = self.resolve_mapped_row("medical_record", old_id, MedicalCase)
            if skip:
                self.stats.skipped += 1
                continue
            member_id = self.id_map.get("patient", row["patient_id"])
            if not member_id:
                self.log_skip(f"case patient not mapped old_patient_id={row['patient_id']}")
                continue
            member = Member.all_objects.filter(pk=member_id).first()
            if not member:
                self.log_skip(f"member missing id={member_id}")
                continue
            if not User.objects.filter(pk=member.user_id).exists():
                self.log_skip(f"case user missing user_id={member.user_id}")
                continue
            if self.dry_run:
                self.id_map.set("medical_record", old_id, old_id)
                self.stats.migrated += 1
                continue

            extra = migration_extra("aera_medical_record", old_id, visit_date=str(row.get("visit_date") or ""))
            if row.get("notes"):
                extra["notes"] = str(row["notes"])

            def _create(row=row, old_id=old_id, member_id=member_id, member=member, extra=extra):
                case = MedicalCase.all_objects.create(
                    user_id=member.user_id,
                    member_id=member_id,
                    record_type="custom",
                    status=MedicalCase.Status.SUBMITTED,
                    title=(row.get("chief_complaint") or "")[:255],
                    diagnosis_summary=row.get("diagnosis") or "",
                    severity=row.get("severity") or "",
                    case_status=row.get("status") or "",
                    is_deleted=bool(row.get("is_deleted")),
                    deleted_at=row.get("deleted_at"),
                    extra=extra,
                )
                MedicalCase.all_objects.filter(pk=case.pk).update(
                    created_at=row.get("created_at") or case.created_at,
                    updated_at=row.get("updated_at") or case.updated_at,
                )
                return case.id

            try:
                new_id = _create()
                self.id_map.set("medical_record", old_id, new_id)
                self.stats.migrated += 1
            except Exception as exc:
                self.log_fail(f"medical_record:{old_id}", exc)
