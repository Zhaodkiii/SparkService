"""Repair migrated JSON extra fields to iOS-compatible flat [String: String] maps."""

from medical.models import (
    ExaminationReport,
    FollowUp,
    HealthExamReport,
    MedExamDetail,
    MedicalCase,
    MedicationPlan,
    MedicationRecord,
    MedicineBox,
    Prescription,
    Surgery,
    Symptom,
    Visit,
)

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.transforms import extra_needs_client_repair, normalize_client_extra


EXTRA_MODELS = (
    (MedicalCase, "all_objects"),
    (Symptom, "all_objects"),
    (Visit, "all_objects"),
    (Surgery, "all_objects"),
    (FollowUp, "all_objects"),
    (ExaminationReport, "all_objects"),
    (HealthExamReport, "all_objects"),
    (MedicineBox, "all_objects"),
    (Prescription, "all_objects"),
    (MedicationPlan, "all_objects"),
    (MedicationRecord, "all_objects"),
    (MedExamDetail, "objects"),
)


class Command(ZdkMigrateCommand):
    help = "Flatten nested extra.migration dicts to client-compatible string maps"

    def run_migration(self) -> None:
        for model, manager_name in EXTRA_MODELS:
            qs = getattr(model, manager_name).all().only("id", "extra")
            model_label = model._meta.label_lower
            repaired = 0
            for obj in qs.iterator(chunk_size=500):
                if not extra_needs_client_repair(obj.extra):
                    continue
                fixed = normalize_client_extra(obj.extra)
                if self.dry_run:
                    repaired += 1
                    continue
                getattr(model, manager_name).filter(pk=obj.pk).update(extra=fixed)
                repaired += 1
            if repaired:
                self.stdout.write(f"{model_label}: repaired {repaired}")
                self.stats.migrated += repaired
