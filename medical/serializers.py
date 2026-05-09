from datetime import datetime, timedelta, timezone

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from medical.models import (
    ExaminationReport,
    FollowUp,
    HealthExamReport,
    MedExamDetail,
    MedicineBox,
    MedicationPlan,
    MedicationRecord,
    MedicalCase,
    Member,
    Prescription,
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
            "severity",
            "case_status",
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
    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff and value.user_id != request.user.id:
            raise serializers.ValidationError(_("member does not belong to current user"))
        return value

    def validate(self, attrs):
        merged = dict(attrs)
        instance = self.instance
        member = merged.get("member") or (getattr(instance, "member", None) if instance is not None else None)
        medical_record = merged.get("medical_record") if "medical_record" in merged else (
            getattr(instance, "medical_record", None) if instance is not None else None
        )
        request = self.context.get("request")

        if medical_record is not None:
            if request and not request.user.is_staff and medical_record.user_id != request.user.id:
                raise serializers.ValidationError({"medical_record": [_("medical_record does not belong to current user")]})
            if member is not None and medical_record.member_id != member.id:
                raise serializers.ValidationError({"medical_record": [_("medical_record.member mismatch with report.member")]})
        return attrs

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


class MedicineBoxSerializer(serializers.ModelSerializer):
    total_quantity = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    remaining_quantity = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)

    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff and value.user_id != request.user.id:
            raise serializers.ValidationError(_("member does not belong to current user"))
        return value

    def validate(self, attrs):
        merged = dict(attrs)
        if self.instance is not None:
            for field in ("total_quantity", "remaining_quantity"):
                if field not in merged:
                    merged[field] = getattr(self.instance, field)
        if merged.get("remaining_quantity") is not None and merged.get("total_quantity") is not None:
            if merged["remaining_quantity"] > merged["total_quantity"]:
                raise serializers.ValidationError({"remaining_quantity": [_("remaining_quantity cannot exceed total_quantity")]})
        if "generic_name" in attrs and isinstance(attrs["generic_name"], str):
            attrs["generic_name"] = attrs["generic_name"].strip()
        generic = attrs.get("generic_name")
        if generic is None and self.instance is not None:
            generic = self.instance.generic_name
        if not (generic or "").strip():
            raise serializers.ValidationError({"generic_name": [_("generic name is required")]})
        if "medicine_type" in attrs:
            mt = attrs["medicine_type"]
            if mt is None or (isinstance(mt, str) and not mt.strip()):
                attrs["medicine_type"] = None
            elif isinstance(mt, str):
                attrs["medicine_type"] = mt.strip()
        return attrs

    class Meta:
        model = MedicineBox
        fields = (
            "id",
            "user",
            "member",
            "drug_name",
            "medicine_type",
            "generic_name",
            "brand_name",
            "dosage_form",
            "strength",
            "total_quantity",
            "remaining_quantity",
            "unit",
            "expire_date",
            "production_batch",
            "notes",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")


class PrescriptionSerializer(serializers.ModelSerializer):
    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff and value.user_id != request.user.id:
            raise serializers.ValidationError(_("member does not belong to current user"))
        return value

    def validate(self, attrs):
        merged = dict(attrs)
        instance = self.instance
        member = merged.get("member") or (getattr(instance, "member", None) if instance is not None else None)
        medical_case = merged.get("medical_case") if "medical_case" in merged else (
            getattr(instance, "medical_case", None) if instance is not None else None
        )
        request = self.context.get("request")
        if medical_case is not None:
            if request and not request.user.is_staff and medical_case.user_id != request.user.id:
                raise serializers.ValidationError({"medical_case": [_("medical_case does not belong to current user")]})
            if member is not None and medical_case.member_id != member.id:
                raise serializers.ValidationError({"medical_case": [_("medical_case.member mismatch with prescription.member")]})
        return attrs

    class Meta:
        model = Prescription
        fields = (
            "id",
            "user",
            "member",
            "medical_case",
            "prescriber_name",
            "institution_name",
            "prescribed_at",
            "diagnosis",
            "prescription_no",
            "status",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")


class MedicationPlanSerializer(serializers.ModelSerializer):
    dose_value = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        allow_null=True,
        coerce_to_string=False,
    )

    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff and value.user_id != request.user.id:
            raise serializers.ValidationError(_("member does not belong to current user"))
        return value

    def validate(self, attrs):
        merged = dict(attrs)
        instance = self.instance
        member = merged.get("member") or (getattr(instance, "member", None) if instance is not None else None)
        medicine_box = merged.get("medicine_box") if "medicine_box" in merged else (
            getattr(instance, "medicine_box", None) if instance is not None else None
        )
        prescription = merged.get("prescription") if "prescription" in merged else (
            getattr(instance, "prescription", None) if instance is not None else None
        )
        medical_case = merged.get("medical_case") if "medical_case" in merged else (
            getattr(instance, "medical_case", None) if instance is not None else None
        )
        start_date = merged.get("start_date") or (getattr(instance, "start_date", None) if instance is not None else None)
        end_date = merged.get("end_date") if "end_date" in merged else (
            getattr(instance, "end_date", None) if instance is not None else None
        )
        request = self.context.get("request")

        def check_owner(obj, field_name):
            if obj is None:
                return
            if request and not request.user.is_staff and obj.user_id != request.user.id:
                raise serializers.ValidationError({field_name: [_("object does not belong to current user")]})
            if member is not None and getattr(obj, "member_id", None) != member.id:
                raise serializers.ValidationError({field_name: [_("object.member mismatch with plan.member")]})

        check_owner(medicine_box, "medicine_box")
        check_owner(prescription, "prescription")
        check_owner(medical_case, "medical_case")
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({"end_date": [_("end_date cannot be earlier than start_date")]})
        return attrs

    class Meta:
        model = MedicationPlan
        fields = (
            "id",
            "user",
            "member",
            "medical_case",
            "medicine_box",
            "prescription",
            "drug_name",
            "dose_per_time",
            "dose_value",
            "dose_unit",
            "frequency_text",
            "frequency_code",
            "reminder_times",
            "start_date",
            "end_date",
            "duration_days",
            "instructions",
            "reminder_enabled",
            "status",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")


class MedicationRecordSerializer(serializers.ModelSerializer):
    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff and value.user_id != request.user.id:
            raise serializers.ValidationError(_("member does not belong to current user"))
        return value

    def validate(self, attrs):
        merged = dict(attrs)
        instance = self.instance
        member = merged.get("member") or (getattr(instance, "member", None) if instance is not None else None)
        plan = merged.get("plan") if "plan" in merged else (getattr(instance, "plan", None) if instance is not None else None)
        request = self.context.get("request")

        if plan is not None:
            if request and not request.user.is_staff and plan.user_id != request.user.id:
                raise serializers.ValidationError({"plan": [_("plan does not belong to current user")]})
            if member is not None and plan.member_id != member.id:
                raise serializers.ValidationError({"plan": [_("plan.member mismatch with record.member")]})
        return attrs

    class Meta:
        model = MedicationRecord
        fields = (
            "id",
            "user",
            "member",
            "plan",
            "scheduled_at",
            "taken_at",
            "status",
            "planned_dose",
            "actual_dose",
            "dose_sequence",
            "timezone",
            "notes",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")
