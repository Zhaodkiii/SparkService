from django.contrib import admin

from medical.models import (
    ExaminationReport,
    FollowUp,
    HealthExamReport,
    HealthMetricRecord,
    Medication,
    MedicationTakenRecord,
    MedExamDetail,
    MedicalCase,
    ModelChangeLog,
    MedicalReport,
    Member,
    PrescriptionBatch,
    Surgery,
    Symptom,
    Visit,
)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "gender", "relationship", "blood_type", "is_primary", "is_deleted", "updated_at")
    list_filter = ("gender", "is_primary", "is_deleted")
    search_fields = ("name", "relationship", "blood_type", "notes")


@admin.register(MedicalCase)
class MedicalCaseAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "record_type", "status", "title", "hospital_name", "is_deleted")
    list_filter = ("record_type", "status", "is_deleted")
    search_fields = ("title", "hospital_name", "diagnosis_summary")


@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "medical_case", "name", "severity", "body_part", "started_at", "is_deleted")
    list_filter = ("severity", "body_part", "is_deleted")
    search_fields = ("name", "code", "notes")


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "medical_case", "visit_type", "visited_at", "department", "doctor_name", "is_deleted")
    list_filter = ("visit_type", "department", "is_deleted")
    search_fields = ("doctor_name", "visit_no", "source_system_id", "notes")


@admin.register(Surgery)
class SurgeryAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "medical_case", "procedure_name", "performed_at", "surgeon", "is_deleted")
    list_filter = ("incision_level", "asa_class", "is_deleted")
    search_fields = ("procedure_name", "procedure_code", "surgeon", "source_system_id")


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "medical_case", "status", "planned_at", "completed_at", "method", "is_deleted")
    list_filter = ("status", "method", "is_deleted")
    search_fields = ("outcome", "next_action")


@admin.register(ExaminationReport)
class ExaminationReportAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "item_name", "organization_name", "reported_at", "status", "is_deleted")
    list_filter = ("status", "source", "is_deleted")
    search_fields = ("item_name", "organization_name", "doctor_name", "impression")


@admin.register(HealthExamReport)
class HealthExamReportAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "institution_name", "report_no", "exam_date", "exam_type", "status", "is_deleted")
    list_filter = ("exam_type", "source", "status", "is_deleted")
    search_fields = ("institution_name", "report_no", "summary")


@admin.register(MedExamDetail)
class MedExamDetailAdmin(admin.ModelAdmin):
    list_display = ("id", "business_type", "business_id", "member", "item_name", "flag", "result_at", "is_deleted")
    list_filter = ("business_type", "flag", "is_deleted")
    search_fields = ("item_name", "item_code", "result_value", "diagnosis")


@admin.register(MedicalReport)
class MedicalReportAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "title", "report_type", "date", "is_deleted")
    list_filter = ("report_type", "is_deleted")
    search_fields = ("title", "hospital", "doctor")


@admin.register(PrescriptionBatch)
class PrescriptionBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "batch_no", "status", "prescribed_at", "institution_name", "is_deleted")
    list_filter = ("status", "is_deleted")
    search_fields = ("batch_no", "prescriber_name", "institution_name", "diagnosis")


@admin.register(Medication)
class MedicationAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "batch", "drug_name", "frequency_text", "reminder_enabled", "is_deleted")
    list_filter = ("reminder_enabled", "is_deleted")
    search_fields = ("drug_name", "generic_name", "brand_name", "frequency_code")


@admin.register(MedicationTakenRecord)
class MedicationTakenRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "medication", "scheduled_at", "status", "dose_sequence", "is_deleted")
    list_filter = ("status", "timezone", "is_deleted")
    search_fields = ("actual_dose", "notes")


@admin.register(ModelChangeLog)
class ModelChangeLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "member", "entity", "entity_id", "action", "from_status", "to_status", "created_at")
    list_filter = ("entity", "action", "created_at")
    search_fields = ("entity", "trace_id", "operator")


@admin.register(HealthMetricRecord)
class HealthMetricRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "profile_client_uid", "metric_type", "value", "unit", "recorded_at", "is_deleted")
    list_filter = ("metric_type", "is_deleted")
    search_fields = ("profile_client_uid", "metric_type")
