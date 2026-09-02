from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from hospital_care.models.organization import DoctorProfile, Hospital, HospitalDepartment


class ClinicalAgentProfile(models.Model):
    class PublicationStatus(models.TextChoices):
        DRAFT = "draft"
        REVIEW = "review"
        PUBLISHED = "published"
        DISABLED = "disabled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hospital = models.ForeignKey(Hospital, related_name="clinical_agents", on_delete=models.PROTECT)
    doctor = models.ForeignKey(DoctorProfile, related_name="clinical_agents", on_delete=models.PROTECT)
    department = models.ForeignKey(HospitalDepartment, related_name="clinical_agents", on_delete=models.PROTECT)
    scenario_binding = models.ForeignKey(
        "ai_config.AIScenarioModelBinding",
        related_name="clinical_agents",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=128)
    public_summary = models.TextField(blank=True, default="")
    greeting = models.TextField(blank=True, default="")
    service_boundary = models.TextField(blank=True, default="")
    publication_status = models.CharField(
        max_length=16,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
        db_index=True,
    )
    doctor_editable_policy = models.JSONField(default=dict, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    version = models.BigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["hospital", "department", "publication_status"], name="idx_agent_hospital_dept_status"),
        ]

    def clean(self):
        doctor_hospital_id = self.doctor.staff_membership.hospital_id
        if self.hospital_id != doctor_hospital_id:
            raise ValidationError({"hospital": "agent hospital must match doctor hospital"})
        if self.department.hospital_id != self.hospital_id:
            raise ValidationError({"department": "agent department must belong to the same hospital"})

    def __str__(self) -> str:
        return self.name


class ClinicalAgentKnowledgeBinding(models.Model):
    class UsageScope(models.TextChoices):
        HOSPITAL = "hospital"
        DEPARTMENT = "department"
        DOCTOR = "doctor"

    class Status(models.TextChoices):
        ACTIVE = "active"
        DISABLED = "disabled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(ClinicalAgentProfile, related_name="knowledge_bindings", on_delete=models.CASCADE)
    knowledge_base = models.ForeignKey(
        "chat_sync.KnowledgeBase",
        related_name="clinical_agent_bindings",
        on_delete=models.PROTECT,
        db_constraint=False,
    )
    usage_scope = models.CharField(max_length=16, choices=UsageScope.choices, default=UsageScope.DOCTOR)
    sort_order = models.IntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="approved_clinical_knowledge_bindings",
        on_delete=models.PROTECT,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["agent", "knowledge_base"], name="uniq_agent_knowledge_base"),
        ]
