from medical.models import Prescription

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_select
from zdk_migration.lib.transforms import migration_extra


class Command(ZdkMigrateCommand):
    help = "Migrate aera_prescription_batch -> medical_prescription"

    def run_migration(self) -> None:
        rows = old_select(
            "aera_prescription_batch",
            [
                "id", "prescription_no", "hospital_name", "department", "doctor_name", "record_id",
                "patient_id", "pharmacy", "diagnosis", "total_amount", "payment_type", "issued_at",
                "is_deleted", "created_at", "updated_at",
            ],
            order_by="id",
        )
        self.stdout.write(f"Found {len(rows)} prescription batches")
        for row in rows:
            old_id = row["id"]
            skip, _ = self.resolve_mapped_row("prescription_batch", old_id, Prescription)
            if skip:
                self.stats.skipped += 1
                continue
            member_id = self.id_map.get("patient", row.get("patient_id"))
            if not member_id:
                self.log_skip(f"prescription patient not mapped id={row.get('patient_id')}")
                continue
            case_id = self.id_map.get("medical_record", row.get("record_id")) if row.get("record_id") else None
            user_id = None
            if case_id:
                case = Prescription.all_objects.model.medical_case.field.related_model.all_objects.filter(pk=case_id).first()
                user_id = case.user_id if case else None
            if not user_id:
                member = Prescription.all_objects.model.member.field.related_model.all_objects.filter(pk=member_id).first()
                user_id = member.user_id if member else None
            if not user_id:
                self.log_skip(f"prescription user unresolved old_id={old_id}")
                continue
            if self.dry_run:
                self.id_map.set("prescription_batch", old_id, old_id)
                self.stats.migrated += 1
                continue

            extra = migration_extra(
                "aera_prescription_batch",
                old_id,
                department=row.get("department") or "",
                pharmacy=row.get("pharmacy") or "",
                total_amount=str(row.get("total_amount")) if row.get("total_amount") is not None else "",
                payment_type=row.get("payment_type") or "",
            )

            def _create(row=row, old_id=old_id, member_id=member_id, case_id=case_id, user_id=user_id, extra=extra):
                obj = Prescription.all_objects.create(
                    user_id=user_id,
                    member_id=member_id,
                    medical_case_id=case_id,
                    prescriber_name=row.get("doctor_name") or "",
                    institution_name=row.get("hospital_name") or "",
                    prescribed_at=row.get("issued_at"),
                    diagnosis=row.get("diagnosis") or "",
                    prescription_no=row.get("prescription_no") or "",
                    status=Prescription.Status.ACTIVE,
                    is_deleted=bool(row.get("is_deleted")),
                    deleted_at=row.get("deleted_at"),
                    extra=extra,
                )
                Prescription.all_objects.filter(pk=obj.pk).update(
                    created_at=row.get("created_at") or obj.created_at,
                    updated_at=row.get("updated_at") or obj.updated_at,
                )
                return obj.id

            try:
                new_id = _create()
                self.id_map.set("prescription_batch", old_id, new_id)
                self.stats.migrated += 1
            except Exception as exc:
                self.log_fail(f"prescription_batch:{old_id}", exc)
