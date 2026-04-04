from django.contrib import admin

from medical.models import ExaminationReport, HealthMetricRecord, MedicalCase, MedicalReport, Member, Prescription


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "relationship", "is_primary", "is_deleted", "updated_at")
    list_filter = ("gender", "is_primary", "is_deleted")
    search_fields = ("name", "relationship")


@admin.register(MedicalCase)
class MedicalCaseAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "title", "severity", "visit_date", "is_deleted")
    list_filter = ("severity", "is_deleted")
    search_fields = ("title", "chief_complaint", "diagnosis")


@admin.register(ExaminationReport)
class ExaminationReportAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "report_name", "check_type", "date", "is_deleted")
    list_filter = ("is_deleted",)
    search_fields = ("report_name", "check_type", "conclusion")


@admin.register(MedicalReport)
class MedicalReportAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "title", "report_type", "date", "is_deleted")
    list_filter = ("report_type", "is_deleted")
    search_fields = ("title", "hospital", "doctor")


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "drug_name", "status", "start_date", "end_date", "is_deleted")
    list_filter = ("status", "is_deleted")
    search_fields = ("drug_name", "dosage", "frequency")


@admin.register(HealthMetricRecord)
class HealthMetricRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "profile_client_uid", "metric_type", "value", "unit", "recorded_at", "is_deleted")
    list_filter = ("metric_type", "is_deleted")
    search_fields = ("profile_client_uid", "metric_type")
