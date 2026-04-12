from datetime import datetime, timedelta, timezone

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from medical.models import (
    ExaminationReport,
    FollowUp,
    HealthExamReport,
    MedExamDetail,
    Medication,
    MedicationTakenRecord,
    MedicalCase,
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
            "user",
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
        read_only_fields = ("id", "user", "created_at", "updated_at")


class MedicalCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalCase
        fields = (
            "id",
            "user",
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
        read_only_fields = ("id", "user", "created_at", "updated_at")


class SymptomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Symptom
        fields = (
            "id",
            "user",
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
        read_only_fields = ("id", "user", "created_at", "updated_at")


class VisitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visit
        fields = (
            "id",
            "user",
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
        read_only_fields = ("id", "user", "created_at", "updated_at")


class SurgerySerializer(serializers.ModelSerializer):
    class Meta:
        model = Surgery
        fields = (
            "id",
            "user",
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
        read_only_fields = ("id", "user", "created_at", "updated_at")


class FollowUpSerializer(serializers.ModelSerializer):
    class Meta:
        model = FollowUp
        fields = (
            "id",
            "user",
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
        read_only_fields = ("id", "user", "created_at", "updated_at")


class ExaminationReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExaminationReport
        fields = (
            "id",
            "user",
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
        read_only_fields = ("id", "user", "created_at", "updated_at")


class HealthExamReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthExamReport
        fields = (
            "id",
            "user",
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
        read_only_fields = ("id", "user", "created_at", "updated_at")


class MedExamDetailSerializer(serializers.ModelSerializer):
    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff and value.user_id != request.user.id:
            raise serializers.ValidationError(_("member does not belong to current user"))
        return value

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


class PrescriptionBatchSerializer(serializers.ModelSerializer):
    # 容错处理：允许客户端不传/传空/传错，统一在 validate_status 回落到 ACTIVE。
    status = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_batch_no(self, value):
        if value == "":
            return None
        return value

    def validate_status(self, value):
        normalized = (value or "").strip().lower()
        allowed = {
            PrescriptionBatch.Status.ACTIVE,
            PrescriptionBatch.Status.AUDITED,
            PrescriptionBatch.Status.REJECTED,
            PrescriptionBatch.Status.COMPLETED,
            PrescriptionBatch.Status.CANCELLED,
        }
        if not normalized or normalized not in allowed:
            return PrescriptionBatch.Status.ACTIVE
        return normalized

    class Meta:
        model = PrescriptionBatch
        fields = (
            "id",
            "user",
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
        read_only_fields = ("id", "user", "created_at", "updated_at")


class MedicationSerializer(serializers.ModelSerializer):
    # JSON numbers for iOS Codable (Double); DRF default coerces Decimal to string.
    dose_value = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        allow_null=True,
        coerce_to_string=False,
    )

    class Meta:
        model = Medication
        fields = (
            "id",
            "user",
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
        # user 与其它医疗模型一致：由服务端写入，组合创建等入口通过 save(user=request.user) 注入
        read_only_fields = ("id", "user", "created_at", "updated_at")


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
