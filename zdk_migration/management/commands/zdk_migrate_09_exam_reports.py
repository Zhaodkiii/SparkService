from medical.models import ExaminationReport, MedExamDetail

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_fetch_all, old_select
from zdk_migration.lib.transforms import char_field_with_overflow, migration_extra, truncate_char


class Command(ZdkMigrateCommand):
    help = "Migrate examination reports and imaging/pathology/lab details"

    def run_migration(self) -> None:
        reports = old_select(
            "aera_exam_report",
            [
                "id", "record_id", "patient_id", "user_id", "category", "subcategory", "date",
                "report_name", "check_type", "conclusion", "doctor_advice", "physical_exam",
                "is_deleted", "created_at",
            ],
            order_by="id",
        )
        self.stdout.write(f"Found {len(reports)} exam reports")
        for row in reports:
            old_id = row["id"]
            skip, mapped_id = self.resolve_mapped_row("exam_report", old_id, ExaminationReport)
            if skip and mapped_id:
                report = ExaminationReport.all_objects.get(pk=mapped_id)
                self._migrate_details(old_id, mapped_id, report.member_id, report.user_id)
                self.stats.skipped += 1
                continue

            member_id = self.id_map.get("patient", row.get("patient_id"))
            if not member_id:
                self.log_skip(f"exam_report patient not mapped id={row.get('patient_id')}")
                continue
            case_id = self.id_map.get("medical_record", row.get("record_id")) if row.get("record_id") else None
            user_id = row.get("user_id")
            if self.dry_run:
                self.id_map.set("exam_report", old_id, old_id)
                self.stats.migrated += 1
                continue

            extra = migration_extra("aera_exam_report", old_id, check_type=row.get("check_type") or "", doctor_advice=row.get("doctor_advice") or "")

            def _create_report(row=row, old_id=old_id, member_id=member_id, case_id=case_id, user_id=user_id, extra=extra):
                report = ExaminationReport.all_objects.create(
                    user_id=user_id,
                    member_id=member_id,
                    medical_record_id=case_id,
                    category=row.get("category") or "",
                    sub_category=row.get("subcategory") or "",
                    item_name=(row.get("report_name") or "exam")[:255],
                    performed_at=row.get("date"),
                    reported_at=row.get("date"),
                    findings=row.get("physical_exam") or "",
                    impression=row.get("conclusion") or "",
                    source=ExaminationReport.Source.MANUAL,
                    status=ExaminationReport.Status.COMPLETED,
                    is_deleted=bool(row.get("is_deleted")),
                    extra=extra,
                )
                ExaminationReport.all_objects.filter(pk=report.pk).update(created_at=row.get("created_at") or report.created_at)
                return report.id

            try:
                new_report_id = _create_report()
                self.id_map.set("exam_report", old_id, new_report_id)
                self.stats.migrated += 1
            except Exception as exc:
                self.log_fail(f"exam_report:{old_id}", exc)
                continue

            self._migrate_details(old_id, new_report_id, member_id, user_id)

    def _migrate_details(self, old_report_id, new_report_id, member_id, user_id) -> None:
        self._migrate_imaging(old_report_id, new_report_id, member_id, user_id)
        self._migrate_pathology(old_report_id, new_report_id, member_id, user_id)
        self._migrate_lab_data(old_report_id, new_report_id, member_id, user_id)

    def _detail_exists(self, *, legacy_table: str, legacy_id) -> bool:
        needle = f'"migration_legacy_table": "{legacy_table}"'
        legacy_id_needle = f'"migration_legacy_id": "{legacy_id}"'
        return MedExamDetail.objects.filter(extra__contains=needle).filter(extra__contains=legacy_id_needle).exists()

    def _migrate_imaging(self, old_report_id, new_report_id, member_id, user_id) -> None:
        rows = old_fetch_all("SELECT * FROM aera_imaging WHERE sheet_id = %s", (old_report_id,))
        for row in rows:
            legacy_id = row["id"]
            if self._detail_exists(legacy_table="aera_imaging", legacy_id=legacy_id):
                continue
            if self.dry_run:
                return

            findings = row.get("findings") or ""
            result_value, overflow = char_field_with_overflow(
                findings,
                max_length=255,
                overflow_key="findings",
            )
            extra = migration_extra("aera_imaging", legacy_id, legacy_type="imaging", **overflow)

            def _create(row=row, result_value=result_value, extra=extra):
                MedExamDetail.objects.create(
                    business_type=MedExamDetail.BusinessType.EXAMINATION_REPORT,
                    business_id=new_report_id,
                    member_id=member_id,
                    category=truncate_char(row.get("modality") or "imaging", 128),
                    item_name=truncate_char(row.get("modality") or "imaging", 255),
                    modality=truncate_char(row.get("modality") or "", 32),
                    body_part=truncate_char(row.get("body_part") or "", 128),
                    result_value=result_value,
                    diagnosis=row.get("impression") or "",
                    flag=truncate_char(row.get("status") or "", 16),
                    extra=extra,
                    is_deleted=bool(row.get("is_deleted")),
                )

            if self.run_safe(f"imaging:{legacy_id}", _create):
                self.stats.migrated += 1

    def _migrate_pathology(self, old_report_id, new_report_id, member_id, user_id) -> None:
        rows = old_fetch_all("SELECT * FROM aera_pathology WHERE sheet_id = %s", (old_report_id,))
        for row in rows:
            legacy_id = row["id"]
            if self._detail_exists(legacy_table="aera_pathology", legacy_id=legacy_id):
                continue
            if self.dry_run:
                return

            def _create(row=row, legacy_id=legacy_id):
                MedExamDetail.objects.create(
                    business_type=MedExamDetail.BusinessType.EXAMINATION_REPORT,
                    business_id=new_report_id,
                    member_id=member_id,
                    category="pathology",
                    item_name=truncate_char(row.get("specimen") or "pathology", 255),
                    result_value=truncate_char(row.get("specimen") or "", 255),
                    diagnosis=row.get("diagnosis") or "",
                    flag=truncate_char(row.get("status") or "", 16),
                    extra=migration_extra("aera_pathology", legacy_id, comment=row.get("comment") or "", legacy_type="pathology"),
                    is_deleted=bool(row.get("is_deleted")),
                )

            if self.run_safe(f"pathology:{legacy_id}", _create):
                self.stats.migrated += 1

    def _migrate_lab_data(self, old_report_id, new_report_id, member_id, user_id) -> None:
        rows = old_fetch_all(
            "SELECT * FROM aera_lab_datum WHERE sheet_id = %s ORDER BY sort_order, id",
            (old_report_id,),
        )
        for row in rows:
            legacy_id = row["id"]
            if self._detail_exists(legacy_table="aera_lab_datum", legacy_id=legacy_id):
                continue
            if self.dry_run:
                return

            def _create(row=row, legacy_id=legacy_id):
                MedExamDetail.objects.create(
                    business_type=MedExamDetail.BusinessType.EXAMINATION_REPORT,
                    business_id=new_report_id,
                    member_id=member_id,
                    category="lab",
                    item_name=truncate_char(row.get("item_name") or "lab", 255),
                    result_value=truncate_char(row.get("value_text") or "", 255),
                    unit=truncate_char(row.get("unit_text") or "", 64),
                    reference_range=truncate_char(row.get("ref_text") or "", 255),
                    flag=truncate_char(row.get("status") or "", 16),
                    sort_order=row.get("sort_order") or 0,
                    extra=migration_extra("aera_lab_datum", legacy_id, legacy_type="lab"),
                    is_deleted=bool(row.get("is_deleted")),
                )

            if self.run_safe(f"lab_datum:{legacy_id}", _create):
                self.stats.migrated += 1
