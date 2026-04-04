import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class MedicalBaseModel(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="%(class)s_items", on_delete=models.CASCADE, db_index=True)
    client_uid = models.UUIDField(default=uuid.uuid4, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        if self.is_deleted:
            return
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


class Member(MedicalBaseModel):
    class Gender(models.TextChoices):
        MALE = "male"
        FEMALE = "female"
        OTHER = "other"
        UNKNOWN = "unknown"

    name = models.CharField(max_length=64)
    age = models.PositiveIntegerField(default=0)
    gender = models.CharField(max_length=16, choices=Gender.choices, default=Gender.UNKNOWN)
    relationship = models.CharField(max_length=64, default="self")
    avatar = models.URLField(blank=True, default="")
    birth_date = models.DateField(null=True, blank=True)
    is_primary = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-is_primary", "-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "client_uid"], name="uniq_member_user_client_uid"),
        ]

    def __str__(self):
        return f"{self.name}({self.relationship})"


class MedicalCase(MedicalBaseModel):
    class Severity(models.TextChoices):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        UNKNOWN = "unknown"

    member = models.ForeignKey(Member, related_name="medical_cases", on_delete=models.CASCADE, db_index=True)
    title = models.CharField(max_length=255)
    chief_complaint = models.CharField(max_length=255, blank=True, default="")
    diagnosis = models.CharField(max_length=255, blank=True, default="")
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.UNKNOWN)
    visit_date = models.DateTimeField()
    status = models.CharField(max_length=64, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-visit_date", "-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "client_uid"], name="uniq_case_user_client_uid"),
        ]


class ExaminationReport(MedicalBaseModel):
    member = models.ForeignKey(Member, related_name="examination_reports", on_delete=models.CASCADE, db_index=True)
    medical_case = models.ForeignKey(
        MedicalCase, related_name="examination_reports", on_delete=models.SET_NULL, null=True, blank=True, db_index=True
    )
    category = models.CharField(max_length=64, blank=True, default="")
    subcategory = models.CharField(max_length=64, blank=True, default="")
    report_name = models.CharField(max_length=255)
    check_type = models.CharField(max_length=128, blank=True, default="")
    conclusion = models.TextField(blank=True, default="")
    doctor_advice = models.TextField(blank=True, default="")
    date = models.DateTimeField()

    class Meta:
        ordering = ["-date", "-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "client_uid"], name="uniq_exam_user_client_uid"),
        ]


class MedicalReport(MedicalBaseModel):
    member = models.ForeignKey(Member, related_name="medical_reports", on_delete=models.CASCADE, db_index=True)
    medical_case = models.ForeignKey(
        MedicalCase, related_name="medical_reports", on_delete=models.SET_NULL, null=True, blank=True, db_index=True
    )
    report_type = models.CharField(max_length=64, blank=True, default="")
    title = models.CharField(max_length=255)
    hospital = models.CharField(max_length=255, blank=True, default="")
    doctor = models.CharField(max_length=128, blank=True, default="")
    content = models.TextField(blank=True, default="")
    date = models.DateTimeField()

    class Meta:
        ordering = ["-date", "-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "client_uid"], name="uniq_medical_report_user_client_uid"),
        ]


class Prescription(MedicalBaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active"
        COMPLETED = "completed"
        STOPPED = "stopped"

    member = models.ForeignKey(Member, related_name="prescriptions", on_delete=models.CASCADE, db_index=True)
    medical_case = models.ForeignKey(
        MedicalCase, related_name="prescriptions", on_delete=models.SET_NULL, null=True, blank=True, db_index=True
    )
    drug_name = models.CharField(max_length=128)
    dosage = models.CharField(max_length=128, blank=True, default="")
    frequency = models.CharField(max_length=128, blank=True, default="")
    duration_days = models.PositiveIntegerField(default=0)
    instructions = models.TextField(blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "client_uid"], name="uniq_prescription_user_client_uid"),
        ]


class HealthMetricRecord(MedicalBaseModel):
    profile_client_uid = models.UUIDField(db_index=True)
    metric_type = models.CharField(max_length=64, db_index=True)
    value = models.FloatField(default=0)
    unit = models.CharField(max_length=32, default="")
    recorded_at = models.DateTimeField(db_index=True)
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-recorded_at", "-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "client_uid"], name="uniq_health_metric_user_client_uid"),
        ]
