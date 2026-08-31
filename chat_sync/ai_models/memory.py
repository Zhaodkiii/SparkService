from __future__ import annotations

from django.conf import settings
from django.db import models


class MemoryScope(models.TextChoices):
    ACCOUNT = "account", "Account"
    MEMBER = "member", "Member"
    AGENT = "agent", "Agent"
    THREAD = "thread", "Thread"


class MemoryLayer(models.TextChoices):
    L2 = "L2", "L2"
    L3 = "L3", "L3"


class MemoryType(models.TextChoices):
    PREFERENCE = "preference", "Preference"
    PERSONAL_FACT = "personal_fact", "Personal Fact"
    MEMBER_FACT = "member_fact", "Member Fact"
    HEALTH_PREFERENCE = "health_preference", "Health Preference"
    INSTRUCTION = "instruction", "Instruction"
    CONVERSATION_SUMMARY = "conversation_summary", "Conversation Summary"


class MemorySource(models.TextChoices):
    USER = "user", "User"
    AI = "ai", "AI"
    SYSTEM = "system", "System"
    IMPORT = "import", "Import"


class MemoryConfirmationStatus(models.TextChoices):
    NOT_REQUIRED = "not_required", "Not Required"
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    REJECTED = "rejected", "Rejected"


class MemoryStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CANDIDATE = "candidate", "Candidate"
    SUPERSEDED = "superseded", "Superseded"
    EXPIRED = "expired", "Expired"


class MemorySensitivity(models.TextChoices):
    NORMAL = "normal", "Normal"
    SENSITIVE = "sensitive", "Sensitive"
    HEALTH = "health", "Health"
    IDENTITY = "identity", "Identity"


class MemoryMutationOperation(models.TextChoices):
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    CONFIRM = "confirm", "Confirm"
    REJECT = "reject", "Reject"
    DELETE = "delete", "Delete"


class AIMemory(models.Model):
    """Authoritative memory entry. Client-stable UUID primary key."""

    id = models.UUIDField(primary_key=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_memories",
    )
    scope = models.CharField(max_length=16, choices=MemoryScope.choices, default=MemoryScope.ACCOUNT)
    scope_key = models.CharField(max_length=160)
    member_id = models.IntegerField(null=True, blank=True, db_index=True)
    agent_key = models.CharField(max_length=128, null=True, blank=True)
    thread_id = models.UUIDField(null=True, blank=True, db_index=True)
    layer = models.CharField(max_length=8, choices=MemoryLayer.choices, default=MemoryLayer.L3)
    document_key = models.CharField(max_length=32)
    section_key = models.CharField(max_length=64, default="general")
    memory_type = models.CharField(max_length=32, choices=MemoryType.choices, default=MemoryType.PREFERENCE)
    normalized_key = models.CharField(max_length=128)
    dedup_key = models.CharField(max_length=64, null=True, blank=True)
    title = models.CharField(max_length=128, blank=True, default="")
    content = models.TextField()
    structured_value = models.JSONField(default=dict, blank=True)
    is_pinned = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    content_hash = models.CharField(max_length=64, default="")
    source = models.CharField(max_length=16, choices=MemorySource.choices, default=MemorySource.USER)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    confirmation_status = models.CharField(
        max_length=16,
        choices=MemoryConfirmationStatus.choices,
        default=MemoryConfirmationStatus.NOT_REQUIRED,
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    sensitivity = models.CharField(
        max_length=16,
        choices=MemorySensitivity.choices,
        default=MemorySensitivity.NORMAL,
    )
    status = models.CharField(max_length=16, choices=MemoryStatus.choices, default=MemoryStatus.ACTIVE)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supersedes",
    )
    created_by_run = models.ForeignKey(
        "chat_sync.ChatRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_memories",
        db_constraint=False,
    )
    origin_device_id_hash = models.CharField(max_length=64, null=True, blank=True)
    last_device_id_hash = models.CharField(max_length=64, null=True, blank=True)
    revision = models.BigIntegerField(default=1)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    server_updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "chat_sync_ai_memory"
        constraints = [
            models.UniqueConstraint(fields=("user", "id"), name="uniq_aimem_user_id"),
            models.UniqueConstraint(fields=("user", "dedup_key"), name="uniq_aimem_user_dedup"),
        ]
        indexes = [
            models.Index(fields=["user", "server_updated_at", "id"], name="idx_aimem_user_sync"),
            models.Index(fields=["user", "scope_key", "is_deleted", "status"], name="idx_aimem_user_scope"),
            models.Index(fields=["user", "memory_type", "normalized_key"], name="idx_aimem_user_type"),
            models.Index(fields=["expires_at", "is_deleted", "status"], name="idx_aimem_expires"),
            models.Index(fields=["superseded_by"], name="idx_aimem_superseded"),
            models.Index(fields=["user", "layer", "document_key", "is_deleted"], name="idx_aimem_user_doc"),
        ]


class AIMemoryMutationReceipt(models.Model):
    """Push / tool-write idempotency receipt. Independent from knowledge receipts."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_memory_mutation_receipts",
    )
    mutation_id = models.UUIDField()
    memory_id = models.UUIDField(db_index=True)
    operation = models.CharField(max_length=16, choices=MemoryMutationOperation.choices)
    request_hash = models.CharField(max_length=64)
    base_revision = models.BigIntegerField(null=True, blank=True)
    result_revision = models.BigIntegerField(default=0)
    result_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "chat_sync_ai_memory_mutation_receipt"
        constraints = [
            models.UniqueConstraint(fields=("user", "mutation_id"), name="uniq_aimrcpt_user_mut"),
        ]
        indexes = [
            models.Index(fields=["user", "memory_id"], name="idx_aimrcpt_user_mem"),
        ]
