from datetime import datetime, timedelta, timezone

from django.contrib.auth.models import User
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from file_manager.business_relations import bind_files_to_business
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
    MemberMedicalProfile,
    MemberMedicalKeyIndicatorRecord,
    MemberModuleSetting,
    Prescription,
    Surgery,
    Symptom,
    UserMemberBinding,
    Visit,
)
from medical.services import member_binding_service as binding_service
from medical.services.medicine_cabinet_service import medicine_box_in_family_cabinet


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


class MemberMedicalProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemberMedicalProfile
        fields = (
            "id",
            "user",
            "member",
            "chronic_conditions",
            "allergies",
            "allergy_details",
            "allergy_history",
            "family_history",
            "smoking_profile",
            "drinking_profile",
            "exercise_profile",
            "sleep_hours",
            "medication_focus",
            "surgery_focus",
            "exam_focus",
            "symptom_follow_up_focus",
            "notes",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at", "medication_focus", "surgery_focus", "symptom_follow_up_focus")

    def to_representation(self, instance):
        payload = super().to_representation(instance)
        for key in ("smoking_profile", "drinking_profile", "exercise_profile"):
            if payload.get(key) == {}:
                payload.pop(key, None)
        return payload

    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff:
            if binding_service.get_active_binding(user=request.user, member_id=value.id) is None:
                raise serializers.ValidationError(_("member does not belong to current user"))
        return value


class MemberModuleSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemberModuleSetting
        fields = (
            "id",
            "user",
            "member",
            "module_code",
            "is_enabled",
            "is_completed",
            "display_order",
            "summary_text",
            "detail_data",
            "completed_at",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")

    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff:
            if binding_service.get_active_binding(user=request.user, member_id=value.id) is None:
                raise serializers.ValidationError(_("member does not belong to current user"))
        return value


class MemberKeyIndicatorDetailWriteSerializer(serializers.Serializer):
    category = serializers.CharField(required=False, allow_blank=True, default="")
    sub_category = serializers.CharField(required=False, allow_blank=True, default="")
    item_name = serializers.CharField()
    item_code = serializers.CharField(required=False, allow_blank=True, default="")
    result_value = serializers.CharField(required=False, allow_blank=True, default="")
    unit = serializers.CharField(required=False, allow_blank=True, default="")
    reference_range = serializers.CharField(required=False, allow_blank=True, default="")
    flag = serializers.CharField(required=False, allow_blank=True, default="")
    result_at = serializers.DateTimeField(required=False, allow_null=True)
    modality = serializers.CharField(required=False, allow_blank=True, default="")
    body_part = serializers.CharField(required=False, allow_blank=True, default="")
    diagnosis = serializers.CharField(required=False, allow_blank=True, default="")
    extra = serializers.DictField(required=False, default=dict)
    sort_order = serializers.IntegerField(required=False, default=0)


class MemberMedicalKeyIndicatorRecordSerializer(serializers.ModelSerializer):
    details = MemberKeyIndicatorDetailWriteSerializer(many=True, required=False, write_only=True)
    detail_rows = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MemberMedicalKeyIndicatorRecord
        fields = (
            "id",
            "user",
            "member",
            "source",
            "scenario",
            "recorded_at",
            "qa_session_id",
            "title",
            "summary",
            "extra",
            "details",
            "detail_rows",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at", "detail_rows")

    def validate_member(self, value):
        request = self.context.get("request")
        if request and not request.user.is_staff:
            if binding_service.get_active_binding(user=request.user, member_id=value.id) is None:
                raise serializers.ValidationError(_("member does not belong to current user"))
        return value

    def get_detail_rows(self, instance):
        rows = MedExamDetail.objects.filter(
            business_type=MedExamDetail.BusinessType.KEY_INDICATOR,
            business_id=instance.id,
            is_deleted=False,
        ).order_by("sort_order", "id")
        return MedExamDetailSerializer(rows, many=True, context=self.context).data

    def create(self, validated_data):
        details = validated_data.pop("details", [])
        instance = super().create(validated_data)
        self._replace_details(instance, details)
        return instance

    def update(self, instance, validated_data):
        details = validated_data.pop("details", None)
        instance = super().update(instance, validated_data)
        if details is not None:
            self._replace_details(instance, details)
        return instance

    def _replace_details(self, instance, details):
        existing = MedExamDetail.objects.filter(
            business_type=MedExamDetail.BusinessType.KEY_INDICATOR,
            business_id=instance.id,
            is_deleted=False,
        )
        for row in existing:
            row.is_deleted = True
            row.save(update_fields=["is_deleted", "updated_at"])

        payloads = []
        for index, detail in enumerate(details):
            payloads.append(
                MedExamDetail(
                    business_type=MedExamDetail.BusinessType.KEY_INDICATOR,
                    business_id=instance.id,
                    member=instance.member,
                    category=detail.get("category", ""),
                    sub_category=detail.get("sub_category", ""),
                    item_name=detail["item_name"],
                    item_code=detail.get("item_code", ""),
                    result_value=detail.get("result_value", ""),
                    unit=detail.get("unit", ""),
                    reference_range=detail.get("reference_range", ""),
                    flag=detail.get("flag", ""),
                    result_at=detail.get("result_at") or instance.recorded_at,
                    modality=detail.get("modality", ""),
                    body_part=detail.get("body_part", ""),
                    diagnosis=detail.get("diagnosis", ""),
                    extra=detail.get("extra", {}),
                    sort_order=detail.get("sort_order", index),
                )
            )
        if payloads:
            MedExamDetail.objects.bulk_create(payloads)


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
        allowed = {
            MedExamDetail.BusinessType.HEALTH_EXAM_REPORT,
            MedExamDetail.BusinessType.EXAMINATION_REPORT,
            MedExamDetail.BusinessType.KEY_INDICATOR,
        }
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
    entry_member_id = serializers.IntegerField(required=False, write_only=True, allow_null=True)
    file_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        write_only=True,
        allow_empty=True,
    )

    def validate_member(self, value):
        if value is None:
            return value
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

        request = self.context.get("request")
        member = attrs.get("member")
        if member is None and self.instance is not None and "member" not in attrs:
            member = self.instance.member

        entry_member_id = attrs.pop("entry_member_id", None)
        if entry_member_id is None and request is not None:
            raw = request.data.get("entry_member_id")
            if raw not in (None, ""):
                try:
                    entry_member_id = int(raw)
                except (TypeError, ValueError) as exc:
                    raise serializers.ValidationError({"entry_member_id": [_("invalid entry_member_id")]}) from exc

        if member is None:
            if entry_member_id is None:
                raise serializers.ValidationError(
                    {"member": [_("entry_member_id is required for household public medicine")]}
                )
            if request and not request.user.is_staff:
                binding = binding_service.get_active_binding(user=request.user, member_id=entry_member_id)
                if binding is None:
                    raise serializers.ValidationError({"entry_member_id": [_("member does not belong to current user")]})
                attrs["_owner_user"] = binding.member.user
        elif member is not None and entry_member_id is None:
            attrs["_owner_user"] = member.user

        return attrs

    def create(self, validated_data):
        file_ids = validated_data.pop("file_ids", [])
        validated_data.pop("_owner_user", None)
        instance = super().create(validated_data)
        self._bind_medicine_box_files(instance, file_ids)
        return instance

    def update(self, instance, validated_data):
        file_ids = validated_data.pop("file_ids", None)
        validated_data.pop("_owner_user", None)
        instance = super().update(instance, validated_data)
        if file_ids is not None:
            self._bind_medicine_box_files(instance, file_ids)
        return instance

    def _bind_medicine_box_files(self, instance, file_ids):
        if not file_ids:
            return
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            bind_files_to_business(request.user, "medicine_box", instance.id, file_ids)

    class Meta:
        model = MedicineBox
        fields = (
            "id",
            "user",
            "member",
            "entry_member_id",
            "file_ids",
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
        extra_kwargs = {"member": {"required": False, "allow_null": True}}


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


class MedicationPlanMedicineBoxField(serializers.PrimaryKeyRelatedField):
    """用药计划关联药箱：已软删除或无效 ID 视为解绑，不阻断保存。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("queryset", MedicineBox.objects.all())
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def get_attribute(self, instance):
        medicine_box_id = getattr(instance, "medicine_box_id", None)
        if not medicine_box_id:
            return None
        return MedicineBox.objects.filter(pk=medicine_box_id).first()

    def to_internal_value(self, data):
        if data is None or data == "":
            return None
        try:
            pk = int(data)
        except (TypeError, ValueError):
            return super().to_internal_value(data)
        return MedicineBox.objects.filter(pk=pk).first()


class MedicationPlanSerializer(HasAttachmentsMixin, serializers.ModelSerializer):
    attachments_business_type = "medication_plan"
    medicine_box = MedicationPlanMedicineBoxField()

    dose_value = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        allow_null=True,
        coerce_to_string=False,
    )
    dose_per_time = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    dose_unit = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")

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
        if instance is not None and instance.medicine_box_id:
            if "medicine_box" not in merged and not MedicineBox.objects.filter(pk=instance.medicine_box_id).exists():
                attrs["medicine_box"] = None
                merged["medicine_box"] = None
        medicine_box = merged.get("medicine_box") if "medicine_box" in merged else (
            self.fields["medicine_box"].get_attribute(instance) if instance is not None else None
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
            obj_member_id = getattr(obj, "member_id", None)
            if field_name == "medicine_box":
                if member is not None and obj_member_id is not None and obj_member_id != member.id:
                    if request and medicine_box_in_family_cabinet(
                        user=request.user,
                        entry_member_id=member.id,
                        medicine_box=obj,
                    ):
                        return
                    raise serializers.ValidationError({field_name: [_("object.member mismatch with plan.member")]})
                return
            if member is not None and obj_member_id != member.id:
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
