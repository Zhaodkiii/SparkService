from collections import defaultdict

import json

from medical.models import HealthExamReport, MedExamDetail

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.error_log import record_migration_issue
from zdk_migration.lib.old_db import old_fetch_all, old_table_exists
from zdk_migration.lib.transforms import combine_reference_range, health_exam_type_to_new, health_item_flag, matches_migration_legacy, migration_extra, normalize_client_extra, parse_json_value, truncate_char


class Command(ZdkMigrateCommand):
    help = "Migrate health exam reports, items, and embed AI item results in extra"

    def run_migration(self) -> None:
        ai_by_item: dict[int, list[dict]] = defaultdict(list)
        if old_table_exists("aera_exam_ai_item_result"):
            for row in old_fetch_all("SELECT * FROM aera_exam_ai_item_result ORDER BY id"):
                item_id = row.get("item_id")
                if item_id:
                    ai_by_item[int(item_id)].append(row)

        headers = old_fetch_all(
            """
            SELECT id, patient_id, user_id, exam_type, institution, exam_date,
                   total_items, abnormal_count, normal_count, source_name, source_meta,
                   is_deleted, deleted_at, created_at, updated_at
            FROM aera_health_exam_report_hdr
            ORDER BY id
            """
        )
        self._discard_removed_legacy_header_maps({str(row["id"]) for row in headers})
        self.stdout.write(f"Found {len(headers)} health exam reports")
        for row in headers:
            old_id = row["id"]
            if not row.get("patient_id"):
                self._discard_null_patient_report(old_id)
                continue

            skip, mapped_id = self._resolve_mapped_health_exam(old_id)
            if skip and mapped_id:
                report = HealthExamReport.all_objects.filter(pk=mapped_id).first()
                if report:
                    self._migrate_items(old_id, mapped_id, report.member_id, ai_by_item)
                self.stats.skipped += 1
                continue

            member_id = self.id_map.get("patient", row.get("patient_id"))
            if not member_id:
                self.log_skip(f"health_exam patient not mapped id={row.get('patient_id')}")
                continue
            if self.dry_run:
                self.id_map.set("health_exam_hdr", old_id, old_id)
                self.stats.migrated += 1
                continue

            source_meta = parse_json_value(row.get("source_meta"), default={})
            extra = migration_extra(
                "aera_health_exam_report_hdr",
                old_id,
                source_name=row.get("source_name") or "",
                source_meta=source_meta,
                stats={
                    "total_items": row.get("total_items"),
                    "abnormal_count": row.get("abnormal_count"),
                    "normal_count": row.get("normal_count"),
                },
            )

            def _create_hdr(row=row, old_id=old_id, member_id=member_id, extra=extra):
                report = HealthExamReport.all_objects.create(
                    user_id=row["user_id"],
                    member_id=member_id,
                    institution_name=row.get("institution") or "",
                    exam_date=(row.get("exam_date").date() if row.get("exam_date") else None),
                    exam_type=health_exam_type_to_new(row.get("exam_type")),
                    source=HealthExamReport.Source.IMPORTED if row.get("source_name") else HealthExamReport.Source.MANUAL,
                    status=HealthExamReport.Status.COMPLETED,
                    is_deleted=bool(row.get("is_deleted")),
                    deleted_at=row.get("deleted_at"),
                    extra=extra,
                )
                HealthExamReport.all_objects.filter(pk=report.pk).update(
                    created_at=row.get("created_at") or report.created_at,
                    updated_at=row.get("updated_at") or report.updated_at,
                )
                return report.id

            try:
                new_hdr_id = _create_hdr()
                self.id_map.set("health_exam_hdr", old_id, new_hdr_id)
                self.stats.migrated += 1
            except Exception as exc:
                self.log_fail(f"health_exam_hdr:{old_id}", exc)
                continue

            self._migrate_items(old_id, new_hdr_id, member_id, ai_by_item)

    def _discard_removed_legacy_header_maps(self, valid_old_ids: set[str]) -> None:
        header_map = getattr(self.id_map, "_data", {}).get("health_exam_hdr", {})
        for old_id in list(header_map):
            if str(old_id) in valid_old_ids:
                continue
            mapped_id = self.id_map.pop("health_exam_hdr", old_id)
            record_migration_issue(
                self.command_name,
                "WARN",
                f"stale health_exam_hdr map cleared old_id={old_id} removed legacy source target_id={mapped_id}",
            )

    def _discard_null_patient_report(self, old_id) -> None:
        mapped_id = self.id_map.get("health_exam_hdr", old_id)
        report_ids: set[int] = set()
        if mapped_id is not None:
            report = HealthExamReport.all_objects.filter(pk=mapped_id).first()
            if report and matches_migration_legacy(report.extra, "aera_health_exam_report_hdr", old_id):
                report_ids.add(report.id)
            self.id_map.pop("health_exam_hdr", old_id)

        reports = HealthExamReport.all_objects.filter(
            extra__migration_legacy_table="aera_health_exam_report_hdr",
            extra__migration_legacy_id=str(old_id),
        )
        report_ids.update(reports.values_list("id", flat=True))

        if report_ids and not self.dry_run:
            MedExamDetail.objects.filter(
                business_type=MedExamDetail.BusinessType.HEALTH_EXAM_REPORT,
                business_id__in=report_ids,
            ).delete()
            HealthExamReport.all_objects.filter(id__in=report_ids).delete()

        for item in old_fetch_all("SELECT id FROM aera_health_exam_report_item WHERE report_id = %s", (old_id,)):
            self.id_map.pop("health_exam_item", item["id"])

    def _resolve_mapped_health_exam(self, old_id) -> tuple[bool, int | str | None]:
        mapped_id = self.id_map.get("health_exam_hdr", old_id)
        if mapped_id is None:
            return False, None
        report = HealthExamReport.all_objects.filter(pk=mapped_id).first()
        if report and matches_migration_legacy(report.extra, "aera_health_exam_report_hdr", old_id):
            return True, mapped_id
        self.id_map.pop("health_exam_hdr", old_id)
        record_migration_issue(
            self.command_name,
            "WARN",
            f"stale health_exam_hdr map cleared old_id={old_id} missing_or_mismatched target_id={mapped_id}",
        )
        return False, None

    def _migrate_items(self, old_hdr_id, new_hdr_id, member_id, ai_by_item) -> None:
        items = old_fetch_all(
            """
            SELECT id, report_id, category, subcategory, item_name, item_code, result_text,
                   result_num, unit, ref_low, ref_high, ref_text, status, severity,
                   description, recommendation, sort_order, extra, is_deleted, deleted_at,
                   created_at, updated_at
            FROM aera_health_exam_report_item
            WHERE report_id = %s
            ORDER BY sort_order, id
            """,
            (old_hdr_id,),
        )
        for row in items:
            old_item_id = row["id"]
            skip, _ = self._resolve_mapped_health_item(old_item_id)
            if skip:
                continue
            item_extra = normalize_client_extra(parse_json_value(row.get("extra"), default={}) or {})
            item_extra.update(
                migration_extra(
                    "aera_health_exam_report_item",
                    old_item_id,
                    severity=row.get("severity") or "",
                    description=row.get("description") or "",
                    recommendation=row.get("recommendation") or "",
                )
            )
            if row.get("result_num") is not None:
                item_extra["result_num"] = str(row.get("result_num"))
            ai_rows = ai_by_item.get(int(old_item_id), [])
            if ai_rows:
                item_extra["ai_analysis"] = json.dumps(
                    [
                        {
                            "disease": ai.get("disease"),
                            "risk_level": ai.get("risk_level"),
                            "clinical_significance": ai.get("clinical_significance"),
                            "personalized_advice": parse_json_value(ai.get("personalized_advice"), []),
                            "legacy_ai_result_id": ai.get("id"),
                        }
                        for ai in ai_rows
                    ],
                    ensure_ascii=False,
                )

            detail = MedExamDetail.objects.create(
                business_type=MedExamDetail.BusinessType.HEALTH_EXAM_REPORT,
                business_id=new_hdr_id,
                member_id=member_id,
                category=row.get("category") or "",
                sub_category=row.get("subcategory") or "",
                item_name=(row.get("item_name") or "item")[:255],
                item_code=row.get("item_code") or "",
                result_value=truncate_char(row.get("result_text") or "", 255),
                unit=truncate_char(row.get("unit") or "", 64),
                reference_range=truncate_char(
                    combine_reference_range(row.get("ref_low"), row.get("ref_high"), row.get("ref_text")),
                    255,
                ),
                flag=truncate_char(health_item_flag(row.get("status")), 16),
                sort_order=row.get("sort_order") or 0,
                extra=item_extra,
                is_deleted=bool(row.get("is_deleted")),
            )
            MedExamDetail.objects.filter(pk=detail.pk).update(
                created_at=row.get("created_at") or detail.created_at,
                updated_at=row.get("updated_at") or detail.updated_at,
            )
            self.id_map.set("health_exam_item", old_item_id, detail.id)

    def _resolve_mapped_health_item(self, old_item_id) -> tuple[bool, int | str | None]:
        mapped_id = self.id_map.get("health_exam_item", old_item_id)
        if mapped_id is None:
            return False, None
        detail = MedExamDetail.objects.filter(pk=mapped_id).first()
        if detail and matches_migration_legacy(detail.extra, "aera_health_exam_report_item", old_item_id):
            return True, mapped_id
        self.id_map.pop("health_exam_item", old_item_id)
        record_migration_issue(
            self.command_name,
            "WARN",
            f"stale health_exam_item map cleared old_id={old_item_id} missing_or_mismatched target_id={mapped_id}",
        )
        return False, None
