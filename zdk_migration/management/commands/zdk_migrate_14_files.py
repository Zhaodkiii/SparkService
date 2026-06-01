import uuid

from django.contrib.auth import get_user_model

from file_manager.models import ManagedFile, ManagedFileBusinessRelation
from medical.models import ExaminationReport, MedicationPlan

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_fetch_all, old_fetch_one
from zdk_migration.lib.transforms import (
    LEGACY_ATTACHMENT_BUSINESS_TYPE_KEYS,
    map_business_relations,
    matches_migration_legacy,
    normalize_business_type_key,
)


class Command(ZdkMigrateCommand):
    help = "Migrate oss_file -> file_manager_managedfile + business relations"

    def run_migration(self) -> None:
        rows = old_fetch_all(
            """
            SELECT id, file_uuid, bucket_name, object_key, original_name, file_ext, mime_type,
                   file_size, file_md5, storage_class, is_public, owner_id, business_type,
                   business_id, status, expire_at, created_at, updated_at
            FROM oss_file
            ORDER BY id
            """
        )
        self.stdout.write(f"Found {len(rows)} oss files")
        User = get_user_model()
        for row in rows:
            old_id = row["id"]
            skip, mapped_uuid = self.resolve_mapped_row("oss_file", old_id, ManagedFile)
            if skip:
                mf = ManagedFile.objects.filter(pk=mapped_uuid).first()
                if mf:
                    self._sync_business_relations(mf, row)
                self.stats.skipped += 1
                continue
            file_uuid = row.get("file_uuid")
            try:
                file_uuid_val = uuid.UUID(str(file_uuid)) if file_uuid else uuid.uuid4()
            except ValueError:
                file_uuid_val = uuid.uuid4()
            if ManagedFile.objects.filter(file_uuid=file_uuid_val).exists():
                mf = ManagedFile.objects.filter(file_uuid=file_uuid_val).first()
                if mf:
                    self.id_map.set("oss_file", old_id, mf.id)
                    self._sync_business_relations(mf, row)
                self.stats.skipped += 1
                continue
            owner_id = row.get("owner_id")
            if not owner_id or not User.objects.filter(pk=owner_id).exists():
                self.log_skip(f"oss_file owner missing old_id={old_id}")
                continue
            is_deleted = int(row.get("status") or 0) != 0
            if self.dry_run:
                self.id_map.set("oss_file", old_id, old_id)
                self.stats.migrated += 1
                continue

            object_key = row.get("object_key") or ""
            bucket = row.get("bucket_name") or ""

            def _create(row=row, old_id=old_id, file_uuid_val=file_uuid_val, owner_id=owner_id, is_deleted=is_deleted, object_key=object_key, bucket=bucket):
                mf = ManagedFile.objects.create(
                    user_id=owner_id,
                    file_uuid=file_uuid_val,
                    file_path=object_key,
                    original_name=row.get("original_name") or "file",
                    file_ext=row.get("file_ext") or "",
                    mime_type=row.get("mime_type") or "application/octet-stream",
                    file_size=row.get("file_size") or 0,
                    file_md5=row.get("file_md5") or "",
                    is_public=bool(row.get("is_public")),
                    object_key=object_key,
                    storage_type="oss",
                    is_deleted=is_deleted,
                )
                ManagedFile.objects.filter(pk=mf.pk).update(
                    created_at=row.get("created_at") or mf.created_at,
                    updated_at=row.get("updated_at") or mf.updated_at,
                )
                self._sync_business_relations(mf, row)
                return mf.id

            try:
                new_id = _create()
                self.id_map.set("oss_file", old_id, new_id)
                self.stats.migrated += 1
            except Exception as exc:
                self.log_fail(f"oss_file:{old_id}", exc)

    def _validated_exam_report_relation(self, old_report_id) -> tuple[str, str] | None:
        mapped_id = self.id_map.get("exam_report", old_report_id)
        if not mapped_id:
            return None
        report = ExaminationReport.all_objects.filter(pk=mapped_id).first()
        if report and matches_migration_legacy(report.extra, "aera_exam_report", old_report_id):
            return ("examination_report", str(mapped_id))
        return None

    def _mapped_business_relations(self, row) -> list[tuple[str, str]]:
        old_type = row.get("business_type")
        old_id = row.get("business_id")
        relations = map_business_relations(old_type, old_id, self.id_map)
        key = normalize_business_type_key(old_type)

        if key in {"report", "examreport"}:
            relations = [relation for relation in relations if relation[0] != "examination_report"]
            validated = self._validated_exam_report_relation(old_id)
            if validated:
                relations.append(validated)

        if key == "examimaging" and not relations:
            imaging = old_fetch_one("SELECT sheet_id FROM aera_imaging WHERE id = %s", (old_id,))
            if imaging:
                validated = self._validated_exam_report_relation(imaging.get("sheet_id"))
                if validated:
                    relations.append(validated)

        if key == "medication":
            plan_id = self.id_map.get("medication", old_id)
            if plan_id and not any(btype == "medicine_box" for btype, _ in relations):
                plan = MedicationPlan.all_objects.filter(pk=plan_id).only("medicine_box_id").first()
                if plan and plan.medicine_box_id:
                    relations.append(("medicine_box", str(plan.medicine_box_id)))

        return list(dict.fromkeys(relations))

    def _sync_business_relations(self, file: ManagedFile, row) -> None:
        if self.dry_run:
            return

        relations = self._mapped_business_relations(row)
        if not relations:
            return

        key = normalize_business_type_key(row.get("business_type"))
        if key in LEGACY_ATTACHMENT_BUSINESS_TYPE_KEYS:
            raw_type = (row.get("business_type") or "").strip()
            legacy_names = {raw_type, raw_type.lower(), key}
            ManagedFileBusinessRelation.objects.filter(
                file_id=file.id,
                business_type__in=[name for name in legacy_names if name],
                business_id=str(row.get("business_id") or ""),
            ).delete()

        key = normalize_business_type_key(row.get("business_type"))
        valid_exam_report_ids = {bid for btype, bid in relations if btype == "examination_report"}
        if key in {"report", "examreport", "examimaging"}:
            ManagedFileBusinessRelation.objects.filter(
                file_id=file.id,
                business_type="examination_report",
            ).exclude(business_id__in=valid_exam_report_ids).delete()
        elif key == "chatattachment":
            ManagedFileBusinessRelation.objects.filter(
                file_id=file.id,
                business_type="examination_report",
            ).delete()

        for btype, bid in relations:
            ManagedFileBusinessRelation.objects.get_or_create(
                file_id=file.id,
                user_id=file.user_id,
                business_type=btype,
                business_id=bid,
            )
