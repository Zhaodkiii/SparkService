from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Hospital(models.Model):
    class ServiceMode(models.TextChoices):
        DEMO = "demo"
        REDIRECT = "redirect"
        INTEGRATED = "integrated"

    class Status(models.TextChoices):
        DRAFT = "draft"
        ACTIVE = "active"
        SUSPENDED = "suspended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    short_name = models.CharField(max_length=64, blank=True, default="")
    grade = models.CharField(max_length=32, blank=True, default="")
    logo_file = models.ForeignKey(
        "file_manager.ManagedFile",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="hospital_logos",
    )
    province_code = models.CharField(max_length=16, blank=True, default="")
    city_code = models.CharField(max_length=16, blank=True, default="")
    district_code = models.CharField(max_length=16, blank=True, default="")
    address = models.CharField(max_length=255)
    service_phone = models.CharField(max_length=32, blank=True, default="")
    emergency_phone = models.CharField(max_length=32, blank=True, default="")
    website_url = models.CharField(max_length=512, blank=True, default="")
    introduction = models.TextField(blank=True, default="")
    registration_redirect_url = models.CharField(max_length=512, blank=True, default="")
    service_mode = models.CharField(max_length=16, choices=ServiceMode.choices, default=ServiceMode.DEMO)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    knowledge_service_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="hospital_knowledge_service_for",
        on_delete=models.PROTECT,
    )
    version = models.BigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "name"], name="idx_hospital_status_name"),
        ]

    def __str__(self) -> str:
        return f"{self.name}({self.code})"


class HospitalDepartment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        HIDDEN = "hidden"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hospital = models.ForeignKey(Hospital, related_name="departments", on_delete=models.PROTECT)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.PROTECT,
    )
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=128)
    short_name = models.CharField(max_length=64, blank=True, default="")
    description = models.TextField(blank=True, default="")
    sort_order = models.IntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hospital", "code"], name="uniq_hospital_department_code"),
        ]
        indexes = [
            models.Index(fields=["hospital", "status", "sort_order"], name="idx_dept_hospital_status"),
        ]

    def clean(self):
        if self.parent_id and self.parent and self.parent.hospital_id != self.hospital_id:
            raise ValidationError({"parent": "parent department must belong to the same hospital"})

    def __str__(self) -> str:
        return f"{self.name}({self.code})"


class HospitalStaffMembership(models.Model):
    class Role(models.TextChoices):
        HOSPITAL_ADMIN = "hospital_admin"
        DOCTOR = "doctor"
        NURSE = "nurse"
        AUDITOR = "auditor"

    class Status(models.TextChoices):
        INVITED = "invited"
        ACTIVE = "active"
        SUSPENDED = "suspended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hospital = models.ForeignKey(Hospital, related_name="staff_memberships", on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="hospital_staff_memberships", on_delete=models.PROTECT)
    role = models.CharField(max_length=32, choices=Role.choices)
    employee_no = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.INVITED)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hospital", "user"], name="uniq_hospital_staff_user"),
        ]
        indexes = [
            models.Index(fields=["user", "status"], name="idx_hospital_staff_user_status"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.hospital_id}:{self.role}"


class DoctorProfile(models.Model):
    class LicenseStatus(models.TextChoices):
        UNVERIFIED = "unverified"
        VERIFIED = "verified"
        SUSPENDED = "suspended"

    class ProfileStatus(models.TextChoices):
        DRAFT = "draft"
        ACTIVE = "active"
        HIDDEN = "hidden"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff_membership = models.OneToOneField(
        HospitalStaffMembership,
        related_name="doctor_profile",
        on_delete=models.PROTECT,
    )
    display_name = models.CharField(max_length=64)
    title = models.CharField(max_length=64, blank=True, default="")
    specialties = models.JSONField(default=list, blank=True)
    introduction = models.TextField(blank=True, default="")
    avatar_file = models.ForeignKey(
        "file_manager.ManagedFile",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="doctor_avatars",
    )
    license_status = models.CharField(max_length=16, choices=LicenseStatus.choices, default=LicenseStatus.UNVERIFIED)
    profile_status = models.CharField(max_length=16, choices=ProfileStatus.choices, default=ProfileStatus.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.staff_membership_id and self.staff_membership.role != HospitalStaffMembership.Role.DOCTOR:
            raise ValidationError({"staff_membership": "doctor profile requires role=doctor"})

    @property
    def hospital(self) -> Hospital:
        return self.staff_membership.hospital

    def __str__(self) -> str:
        return self.display_name


class DoctorDepartmentMembership(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        HIDDEN = "hidden"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    doctor = models.ForeignKey(DoctorProfile, related_name="department_memberships", on_delete=models.CASCADE)
    department = models.ForeignKey(HospitalDepartment, related_name="doctor_memberships", on_delete=models.PROTECT)
    is_primary = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["doctor", "department"], name="uniq_doctor_department"),
        ]

    def clean(self):
        doctor_hospital_id = self.doctor.staff_membership.hospital_id
        if self.department.hospital_id != doctor_hospital_id:
            raise ValidationError({"department": "department must belong to the doctor's hospital"})
