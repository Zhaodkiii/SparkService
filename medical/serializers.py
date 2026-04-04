from datetime import datetime, timedelta, timezone

from rest_framework import serializers

from medical.models import ExaminationReport, HealthMetricRecord, MedicalCase, MedicalReport, Member, Prescription


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
            "client_uid",
            "name",
            "age",
            "gender",
            "relationship",
            "avatar",
            "birth_date",
            "is_primary",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class SyncMemberSerializer(serializers.Serializer):
    client_uid = serializers.UUIDField()
    name = serializers.CharField(max_length=64)
    age = serializers.IntegerField(min_value=0, required=False, default=0)
    gender = serializers.CharField(max_length=16, required=False, allow_blank=True, default=Member.Gender.UNKNOWN)
    relationship = serializers.CharField(max_length=64, required=False, allow_blank=True, default="self")
    avatar = serializers.CharField(required=False, allow_blank=True, default="")
    birth_date = FlexibleDateField(required=False, allow_null=True)
    is_primary = serializers.BooleanField(required=False, default=False)


class MedicalCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalCase
        fields = (
            "id",
            "client_uid",
            "member",
            "title",
            "chief_complaint",
            "diagnosis",
            "severity",
            "visit_date",
            "status",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ExaminationReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExaminationReport
        fields = (
            "id",
            "client_uid",
            "member",
            "medical_case",
            "category",
            "subcategory",
            "report_name",
            "check_type",
            "conclusion",
            "doctor_advice",
            "date",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class MedicalReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalReport
        fields = (
            "id",
            "client_uid",
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


class PrescriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prescription
        fields = (
            "id",
            "client_uid",
            "member",
            "medical_case",
            "drug_name",
            "dosage",
            "frequency",
            "duration_days",
            "instructions",
            "start_date",
            "end_date",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class HealthMetricRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthMetricRecord
        fields = (
            "id",
            "client_uid",
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
    examination_reports = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    medical_reports = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    prescriptions = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    health_metrics = serializers.ListField(child=serializers.DictField(), required=False, default=list)
