from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from hospital_care.models.organization import Hospital, HospitalDepartment


class HospitalKnowledgeBaseProfile(models.Model):
    class VectorStatus(models.TextChoices):
        NOT_BUILT = "not_built"
        CURRENT = "current"
        STALE = "stale"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hospital = models.ForeignKey(Hospital, related_name="knowledge_base_profiles", on_delete=models.PROTECT)
    knowledge_base = models.OneToOneField(
        "chat_sync.KnowledgeBase",
        related_name="hospital_profile",
        on_delete=models.PROTECT,
        db_constraint=False,
    )
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, default="")
    vector_status = models.CharField(
        max_length=16,
        choices=VectorStatus.choices,
        default=VectorStatus.NOT_BUILT,
        db_index=True,
    )
    indexed_revision = models.BigIntegerField(null=True, blank=True)
    embedding_binding = models.ForeignKey(
        "ai_config.AIScenarioModelBinding",
        null=True,
        blank=True,
        related_name="hospital_knowledge_profiles",
        on_delete=models.PROTECT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="created_hospital_knowledge_bases",
        on_delete=models.PROTECT,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="updated_hospital_knowledge_bases",
        on_delete=models.PROTECT,
    )
    version = models.BigIntegerField(default=1)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["hospital", "is_deleted", "name"], name="idx_hkb_hospital_name"),
        ]

    def __str__(self) -> str:
        return self.name


class HospitalKnowledgeBaseDepartment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        HospitalKnowledgeBaseProfile,
        related_name="department_links",
        on_delete=models.CASCADE,
    )
    department = models.ForeignKey(
        HospitalDepartment,
        related_name="knowledge_base_links",
        on_delete=models.PROTECT,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["profile", "department"], name="uniq_hkb_profile_department"),
        ]


class HospitalKnowledgeChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        HospitalKnowledgeBaseProfile,
        related_name="chunks",
        on_delete=models.CASCADE,
    )
    document = models.ForeignKey(
        "chat_sync.KnowledgeDocument",
        related_name="hospital_chunks",
        on_delete=models.PROTECT,
        db_constraint=False,
    )
    document_revision = models.BigIntegerField()
    chunk_index = models.IntegerField()
    content = models.TextField()
    content_hash = models.CharField(max_length=64)
    embedding_binding = models.ForeignKey(
        "ai_config.AIScenarioModelBinding",
        related_name="hospital_knowledge_chunks",
        on_delete=models.PROTECT,
    )
    vector_payload = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["profile", "document", "chunk_index"], name="uniq_hkb_chunk_doc_index"),
        ]
        indexes = [
            models.Index(fields=["profile", "document"], name="idx_hkb_chunk_profile_doc"),
        ]
