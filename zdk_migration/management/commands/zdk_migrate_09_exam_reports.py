from medical.models import ExaminationReport, MedExamDetail

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.error_log import record_migration_issue
from zdk_migration.lib.old_db import old_fetch_all, old_select
from zdk_migration.lib.transforms import (
    char_field_with_overflow,
    matches_migration_legacy,
    migration_extra,
    truncate_char,
)


class Command(ZdkMigrateCommand):
    help = "Migrate examination reports and imaging/pathology/lab details"

    LEGACY_TABLE = "aera_exam_report"
    DETAIL_SOURCES: tuple[tuple[str, str], ...] = (
        ("aera_imaging", "SELECT id FROM aera_imaging WHERE sheet_id = %s"),
        ("aera_pathology", "SELECT id FROM aera_pathology WHERE sheet_id = %s"),
        ("aera_lab_datum", "SELECT id FROM aera_lab_datum WHERE sheet_id = %s"),
    )

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
        self._discard_removed_legacy_maps({str(row["id"]) for row in reports})
        self.stdout.write(f"Found {len(reports)} exam reports")
        for row in reports:
            old_id = row["id"]
            skip, mapped_id = self._resolve_mapped_exam_report(old_id)
            if skip and mapped_id:
                report = ExaminationReport.all_objects.get(pk=mapped_id)
                self._remove_foreign_details(mapped_id, old_id)
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

            extra = migration_extra(
                self.LEGACY_TABLE,
                old_id,
                check_type=row.get("check_type") or "",
                doctor_advice=row.get("doctor_advice") or "",
            )

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

            self._remove_foreign_details(new_report_id, old_id)
            self._migrate_details(old_id, new_report_id, member_id, user_id)

        repaired = self._repair_all_misattached_details()
        if repaired:
            self.stdout.write(f"Removed {repaired} misattached exam report details")

    def _discard_removed_legacy_maps(self, valid_old_ids: set[str]) -> None:
        report_map = getattr(self.id_map, "_data", {}).get("exam_report", {})
        for old_id in list(report_map):
            if str(old_id) in valid_old_ids:
                continue
            mapped_id = self.id_map.pop("exam_report", old_id)
            record_migration_issue(
                self.command_name,
                "WARN",
                f"stale exam_report map cleared old_id={old_id} removed legacy source target_id={mapped_id}",
            )

    def _resolve_mapped_exam_report(self, old_id) -> tuple[bool, int | str | None]:
        mapped_id = self.id_map.get("exam_report", old_id)
        if mapped_id is None:
            return False, None
        report = ExaminationReport.all_objects.filter(pk=mapped_id).first()
        if report and matches_migration_legacy(report.extra, self.LEGACY_TABLE, old_id):
            return True, mapped_id
        self.id_map.pop("exam_report", old_id)
        record_migration_issue(
            self.command_name,
            "WARN",
            f"stale exam_report map cleared old_id={old_id} missing_or_mismatched target_id={mapped_id}",
        )
        return False, None

    def _valid_detail_legacy_ids(self, old_report_id) -> set[tuple[str, str]]:
        valid: set[tuple[str, str]] = set()
        for table, sql in self.DETAIL_SOURCES:
            for row in old_fetch_all(sql, (old_report_id,)):
                valid.add((table, str(row["id"])))
        return valid

    def _remove_foreign_details(self, new_report_id, old_report_id) -> int:
        valid = self._valid_detail_legacy_ids(old_report_id)
        detail_tables = {table for table, _ in self.DETAIL_SOURCES}
        removed = 0
        details = MedExamDetail.objects.filter(
            business_type=MedExamDetail.BusinessType.EXAMINATION_REPORT,
            business_id=new_report_id,
        )
        for detail in details:
            extra = detail.extra if isinstance(detail.extra, dict) else {}
            table = str(extra.get("migration_legacy_table") or "")
            legacy_id = str(extra.get("migration_legacy_id") or "")
            if table not in detail_tables or not legacy_id:
                continue
            if (table, legacy_id) in valid:
                continue
            if not self.dry_run:
                detail.delete()
            removed += 1
        if removed:
            self.stats.migrated += removed
        return removed

    def _repair_all_misattached_details(self) -> int:
        repaired = 0
        for report in ExaminationReport.all_objects.iterator():
            extra = report.extra if isinstance(report.extra, dict) else {}
            if str(extra.get("migration_legacy_table") or "") != self.LEGACY_TABLE:
                continue
            old_id = extra.get("migration_legacy_id")
            if old_id is None:
                continue
            repaired += self._remove_foreign_details(report.id, old_id)
        return repaired

    def _migrate_details(self, old_report_id, new_report_id, member_id, user_id) -> None:
        self._migrate_imaging(old_report_id, new_report_id, member_id, user_id)
        self._migrate_pathology(old_report_id, new_report_id, member_id, user_id)
        self._migrate_lab_data(old_report_id, new_report_id, member_id, user_id)

    def _detail_exists(self, *, legacy_table: str, legacy_id, new_report_id) -> bool:
        needle = f'"migration_legacy_table": "{legacy_table}"'
        legacy_id_needle = f'"migration_legacy_id": "{legacy_id}"'
        return (
            MedExamDetail.objects.filter(
                business_type=MedExamDetail.BusinessType.EXAMINATION_REPORT,
                business_id=new_report_id,
            )
            .filter(extra__contains=needle)
            .filter(extra__contains=legacy_id_needle)
            .exists()
        )

    def _migrate_imaging(self, old_report_id, new_report_id, member_id, user_id) -> None:
        rows = old_fetch_all("SELECT * FROM aera_imaging WHERE sheet_id = %s", (old_report_id,))
        for row in rows:
            legacy_id = row["id"]
            if self._detail_exists(legacy_table="aera_imaging", legacy_id=legacy_id, new_report_id=new_report_id):
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
            if self._detail_exists(legacy_table="aera_pathology", legacy_id=legacy_id, new_report_id=new_report_id):
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
            if self._detail_exists(legacy_table="aera_lab_datum", legacy_id=legacy_id, new_report_id=new_report_id):
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
