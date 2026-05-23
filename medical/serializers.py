from datetime import datetime, timedelta, timezone

from django.contrib.auth.models import User
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from file_manager.serializers import HasAttachmentsMixin

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
    UserMemberBinding,
    Visit,
)
from medical.services import member_binding_service as binding_service


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
    relationship = serializers.CharField(required=False, write_only=True)

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

    def create(self, validated_data):
        relationship = validated_data.pop("relationship", "self")
        member = super().create(validated_data)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            binding_service.create_owner_binding(
                user=request.user,
                member=member,
                relationship=relationship,
            )
        return member

    def update(self, instance, validated_data):
        validated_data.pop("relationship", None)
        return super().update(instance, validated_data)


class MemberBindingUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserMemberBinding
        fields = ("relationship",)
        extra_kwargs = {"relationship": {"required": True}}


def serialize_member_list_item(member: Member, binding: UserMemberBinding) -> dict:
    caps = binding_service.compute_capabilities(binding)
    return {
        "id": member.id,
        "binding_id": caps.binding_id,
        "name": member.name,
        "gender": member.gender,
        "relationship": caps.relationship,
        "birth_date": member.birth_date,
        "blood_type": member.blood_type,
        "allergies": member.allergies,
        "chronic_conditions": member.chronic_conditions,
        "notes": member.notes,
        "avatar_url": member.avatar_url,
        "is_primary": member.is_primary,
        "binding_role": caps.binding_role,
        "permission": caps.permission,
        "shared_user_count": caps.shared_user_count,
        "can_view": caps.can_view,
        "can_create": caps.can_create,
        "can_share": caps.can_share,
        "can_edit": caps.can_edit,
        "can_delete": caps.can_delete,
        "can_unbind": caps.can_unbind,
        "can_manage_bindings": caps.can_manage_bindings,
        "updated_at": member.updated_at,
    }


def serialize_member_detail(
    member: Member,
    binding: UserMemberBinding,
    *,
    viewer: User,
    include_shared_users: bool,
) -> dict:
    caps = binding_service.compute_capabilities(binding)
    overview = binding_service.member_medical_overview(member.id)
    payload = serialize_member_list_item(member, binding)
    payload.update(
        {
            "medical_overview": overview,
            "shared_users": binding_service.shared_users_payload(
                member_id=member.id,
                viewer=viewer,
                include_details=include_shared_users,
            ),
            "my_binding": {
                "binding_id": caps.binding_id,
                "relationship": caps.relationship,
                "role": caps.binding_role,
                "is_primary": member.is_primary,
            },
        }
    )
    return payload


class MedicalCaseSerializer(serializers.ModelSerializer):
    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff:
            if binding_service.get_active_binding(user=request.user, member_id=value.id) is None:
                raise serializers.ValidationError(_("member does not belong to current user"))
        return value

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


class ExaminationReportSerializer(HasAttachmentsMixin, serializers.ModelSerializer):
    attachments_business_type = "examination_report"
    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff:
            if binding_service.get_active_binding(user=request.user, member_id=value.id) is None:
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

        if medical_record is not None and member is not None and medical_record.member_id != member.id:
            raise serializers.ValidationError({"medical_record": [_("medical_record.member mismatch with report.member")]})
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop("raw_ocr", None)
        return data

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
            "attachments",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")


class HealthExamReportSerializer(HasAttachmentsMixin, serializers.ModelSerializer):
    attachments_business_type = "health_exam_report"

    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff:
            if binding_service.get_active_binding(user=request.user, member_id=value.id) is None:
                raise serializers.ValidationError(_("member does not belong to current user"))
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop("raw_ocr", None)
        return data

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
            "attachments",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")


class MedExamDetailSerializer(serializers.ModelSerializer):
    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff:
            if binding_service.get_active_binding(user=request.user, member_id=value.id) is None:
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


class MedicineBoxSerializer(HasAttachmentsMixin, serializers.ModelSerializer):
    attachments_business_type = "medicine_box"

    total_quantity = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        coerce_to_string=False,
        required=False,
        allow_null=True,
    )

    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff:
            if binding_service.get_active_binding(user=request.user, member_id=value.id) is None:
                raise serializers.ValidationError(_("member does not belong to current user"))
        return value

    def validate(self, attrs):
        if "medicine_name" in attrs and isinstance(attrs["medicine_name"], str):
            attrs["medicine_name"] = attrs["medicine_name"].strip()

        name = attrs.get("medicine_name")
        if name is None and self.instance is not None:
            name = self.instance.medicine_name
        if not (name or "").strip():
            raise serializers.ValidationError({"medicine_name": [_("medicine name is required")]})
        if "total_quantity" in attrs and attrs.get("total_quantity") == "":
            attrs["total_quantity"] = None
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
            "medicine_type",
            "medicine_name",
            "brand_name",
            "dosage_form",
            "strength",
            "dose_unit",
            "total_quantity",
            "expire_date",
            "notes",
            "extra",
            "attachments",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")


class PrescriptionSerializer(HasAttachmentsMixin, serializers.ModelSerializer):
    attachments_business_type = "prescription_batch"

    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff:
            if binding_service.get_active_binding(user=request.user, member_id=value.id) is None:
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
        if medical_case is not None and member is not None and medical_case.member_id != member.id:
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
            "attachments",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")


class MedicationPlanSerializer(HasAttachmentsMixin, serializers.ModelSerializer):
    attachments_business_type = "medication_plan"

    dose_value = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        allow_null=True,
        coerce_to_string=False,
    )

    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff:
            if binding_service.get_active_binding(user=request.user, member_id=value.id) is None:
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
            if member is not None and getattr(obj, "member_id", None) != member.id:
                raise serializers.ValidationError({field_name: [_("object.member mismatch with plan.member")]})

        check_owner(medicine_box, "medicine_box")
        check_owner(prescription, "prescription")
        check_owner(medical_case, "medical_case")
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({"end_date": [_("end_date cannot be earlier than start_date")]})

        ftype = merged.get("frequency_type")
        if ftype is None and instance is not None:
            ftype = instance.frequency_type
        if ftype is None:
            ftype = MedicationPlan.FrequencyType.DAILY

        every_n = merged.get("every_n_days") if "every_n_days" in merged else (
            getattr(instance, "every_n_days", None) if instance is not None else None
        )
        weekdays = merged.get("weekly_weekdays") if "weekly_weekdays" in merged else (
            getattr(instance, "weekly_weekdays", None) if instance is not None else None
        )
        if weekdays is None:
            weekdays = []

        if ftype == MedicationPlan.FrequencyType.EVERY_N_DAYS:
            if every_n is None or every_n < 1:
                raise serializers.ValidationError(
                    {"every_n_days": [_("every_n_days is required and must be >= 1 when frequency_type is every_n_days")]}
                )
            if every_n > 365:
                raise serializers.ValidationError(
                    {"every_n_days": [_("every_n_days must be at most 365")]}
                )
        if ftype == MedicationPlan.FrequencyType.WEEKLY:
            if not weekdays:
                raise serializers.ValidationError(
                    {"weekly_weekdays": [_("weekly_weekdays must be non-empty when frequency_type is weekly")]}
                )
            bad = [d for d in weekdays if not isinstance(d, int) or d < 1 or d > 7]
            if bad:
                raise serializers.ValidationError(
                    {"weekly_weekdays": [_("weekday values must be integers 1–7 (Mon–Sun)")]},
                )

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
            "frequency_type",
            "every_n_days",
            "weekly_weekdays",
            "frequency_text",
            "reminder_times",
            "start_date",
            "end_date",
            "instructions",
            "reminder_enabled",
            "status",
            "extra",
            "attachments",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")


class MedicationRecordSerializer(serializers.ModelSerializer):
    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff:
            if binding_service.get_active_binding(user=request.user, member_id=value.id) is None:
                raise serializers.ValidationError(_("member does not belong to current user"))
        return value

    def validate(self, attrs):
        merged = dict(attrs)
        instance = self.instance
        member = merged.get("member") or (getattr(instance, "member", None) if instance is not None else None)
        plan = merged.get("plan") if "plan" in merged else (getattr(instance, "plan", None) if instance is not None else None)
        request = self.context.get("request")

        if plan is not None and member is not None and plan.member_id != member.id:
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
