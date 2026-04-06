from datetime import datetime, timedelta, timezone

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from medical.models import (
    ExaminationReport,
    FollowUp,
    HealthExamReport,
    HealthMetricRecord,
    MedExamDetail,
    Medication,
    MedicationTakenRecord,
    MedicalCase,
    MedicalReport,
    Member,
    PrescriptionBatch,
    Surgery,
    Symptom,
    Visit,
)


class FlexibleDateField(serializers.DateField):
    """
    Accept standard YYYY-MM-DD and legacy Swift Date numeric payload
    (seconds since 2001-01-01 00:00:00 UTC).
    """

    def to_internal_value(self, value):
        if isinstance(value, (int, float)):
            return self._from_legacy_reference(float(value))
        if isinstance(value, str):
            compact = value.strip()
            if compact:
                try:
                    return self._from_legacy_reference(float(compact))
                except ValueError:
                    pass
        return super().to_internal_value(value)

    @staticmethod
    def _from_legacy_reference(raw_value):
        seconds = raw_value / 1000 if abs(raw_value) > 100_000_000_000 else raw_value
        apple_ref = datetime(2001, 1, 1, tzinfo=timezone.utc)
        return (apple_ref + timedelta(seconds=seconds)).date()


class MemberSerializer(serializers.ModelSerializer):
    birth_date = FlexibleDateField(required=False, allow_null=True)

    class Meta:
        model = Member
        fields = (
            "id",
            "name",
            "gender",
            "relationship",
            "birth_date",
            "blood_type",
            "allergies",
            "chronic_conditions",
            "notes",
            "avatar_url",
            "is_primary",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class SyncMemberSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    name = serializers.CharField(max_length=64)
    gender = serializers.CharField(max_length=16, required=False, allow_blank=True, default=Member.Gender.UNKNOWN)
    relationship = serializers.CharField(max_length=64, required=False, allow_blank=True, default="self")
    birth_date = FlexibleDateField(required=False, allow_null=True)
    blood_type = serializers.CharField(max_length=8, required=False, allow_blank=True, default="")
    allergies = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    chronic_conditions = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    avatar_url = serializers.CharField(required=False, allow_blank=True, default="")
    is_primary = serializers.BooleanField(required=False, default=False)


class MedicalCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalCase
        fields = (
            "id",
            "member",
            "record_type",
            "status",
            "title",
            "hospital_name",
            "age_at_visit",
            "diagnosis_summary",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class SymptomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Symptom
        fields = (
            "id",
            "member",
            "medical_case",
            "name",
            "code",
            "severity",
            "started_at",
            "duration_value",
            "duration_unit",
            "body_part",
            "notes",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class VisitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visit
        fields = (
            "id",
            "member",
            "medical_case",
            "visit_type",
            "visited_at",
            "department",
            "doctor_name",
            "visit_no",
            "source_system_id",
            "notes",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class SurgerySerializer(serializers.ModelSerializer):
    class Meta:
        model = Surgery
        fields = (
            "id",
            "member",
            "medical_case",
            "procedure_name",
            "procedure_code",
            "site",
            "performed_at",
            "surgeon",
            "anesthesia_type",
            "incision_level",
            "asa_class",
            "source_system_id",
            "notes",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class FollowUpSerializer(serializers.ModelSerializer):
    class Meta:
        model = FollowUp
        fields = (
            "id",
            "member",
            "medical_case",
            "planned_at",
            "completed_at",
            "status",
            "method",
            "outcome",
            "next_action",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ExaminationReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExaminationReport
        fields = (
            "id",
            "member",
            "medical_record",
            "category",
            "sub_category",
            "item_name",
            "performed_at",
            "reported_at",
            "organization_name",
            "department_name",
            "doctor_name",
            "findings",
            "impression",
            "source",
            "raw_ocr",
            "status",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class HealthExamReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthExamReport
        fields = (
            "id",
            "member",
            "institution_name",
            "report_no",
            "exam_date",
            "exam_type",
            "summary",
            "source",
            "raw_ocr",
            "status",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class MedExamDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedExamDetail
        fields = (
            "id",
            "business_type",
            "business_id",
            "member",
            "category",
            "sub_category",
            "item_name",
            "item_code",
            "result_value",
            "unit",
            "reference_range",
            "flag",
            "result_at",
            "modality",
            "body_part",
            "diagnosis",
            "extra",
            "sort_order",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_business_type(self, value):
        allowed = {MedExamDetail.BusinessType.HEALTH_EXAM_REPORT, MedExamDetail.BusinessType.EXAMINATION_REPORT}
        if value not in allowed:
            raise serializers.ValidationError(_("unsupported business_type"))
        return value


class MedicalReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalReport
        fields = (
            "id",
            "member",
            "medical_case",
            "report_type",
            "title",
            "hospital",
            "doctor",
            "content",
            "date",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class PrescriptionBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionBatch
        fields = (
            "id",
            "member",
            "medical_case",
            "prescriber_name",
            "institution_name",
            "prescribed_at",
            "diagnosis",
            "batch_no",
            "status",
            "auditor_name",
            "audited_at",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class MedicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medication
        fields = (
            "id",
            "member",
            "batch",
            "generic_name",
            "brand_name",
            "drug_name",
            "dosage_form",
            "strength",
            "route",
            "dose_per_time",
            "dose_value",
            "dose_unit",
            "frequency_code",
            "period",
            "times_per_period",
            "frequency_text",
            "duration_days",
            "instructions",
            "reminder_enabled",
            "reminder_times",
            "sort_order",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class MedicationTakenRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicationTakenRecord
        fields = (
            "id",
            "member",
            "medication",
            "scheduled_at",
            "taken_at",
            "status",
            "dose_sequence",
            "actual_dose",
            "timezone",
            "notes",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class HealthMetricRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthMetricRecord
        fields = (
            "id",
            "profile_client_uid",
            "metric_type",
            "value",
            "unit",
            "recorded_at",
            "note",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class MedicalSnapshotUploadSerializer(serializers.Serializer):
    members = SyncMemberSerializer(many=True, required=False, default=list)
    medical_cases = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    symptoms = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    visits = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    surgeries = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    follow_ups = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    health_exam_reports = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    examination_reports = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    med_exam_details = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    medical_reports = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    prescription_batches = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    medications = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    medication_taken_records = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    health_metrics = serializers.ListField(child=serializers.DictField(), required=False, default=list)
