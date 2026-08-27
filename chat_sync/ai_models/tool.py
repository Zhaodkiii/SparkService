from __future__ import annotations

import uuid

from django.db import models


class ChatToolCall(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        RUNNING = "running", "Running"
        WAITING_FOR_USER = "waiting_for_user", "Waiting for user"
        WAITING_FOR_CLIENT = "waiting_for_client", "Waiting for client"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"
        REJECTED = "rejected", "Rejected"

    run = models.ForeignKey("chat_sync.ChatRun", on_delete=models.CASCADE, related_name="tool_calls")
    tool_call_id = models.CharField(max_length=128)
    tool_name = models.CharField(max_length=128)
    tool_version = models.CharField(max_length=64, blank=True, default="")
    target = models.CharField(max_length=32, blank=True, default="server")
    execution_mode = models.CharField(max_length=32, blank=True, default="immediate")
    arguments = models.JSONField(default=dict)
    round_index = models.PositiveIntegerField(default=0)
    call_index = models.PositiveIntegerField(default=0)
    canonical_name = models.CharField(max_length=128, blank=True, default="")
    arguments_hash = models.CharField(max_length=64, blank=True, default="")
    schema_hash = models.CharField(max_length=64, blank=True, default="")
    policy_version = models.CharField(max_length=32, blank=True, default="")
    execution_key = models.CharField(max_length=160, blank=True, default="", db_index=True)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    result_summary = models.TextField(blank=True, default="")
    result_ref = models.CharField(max_length=512, blank=True, default="")
    result_content = models.TextField(blank=True, default="")
    result_metadata = models.JSONField(default=dict)
    source_refs = models.JSONField(default=list)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.CharField(max_length=512, blank=True, default="")
    retryable = models.BooleanField(default=False)
    provider_index = models.PositiveIntegerField(null=True, blank=True)
    duplicate_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="duplicates")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_sync_ai_tool_call"
        constraints = [models.UniqueConstraint(fields=["run", "tool_call_id"], name="uniq_ai_tool_call_run_id")]
        indexes = [models.Index(fields=["run", "status"], name="idx_ai_tool_run_status")]


class ChatAgentCheckpoint(models.Model):
    class Status(models.TextChoices):
        READY = "ready", "Ready"
        SUPERSEDED = "superseded", "Superseded"

    run = models.OneToOneField("chat_sync.ChatRun", on_delete=models.CASCADE, related_name="agent_checkpoint")
    context_snapshot = models.ForeignKey("chat_sync.ChatTurnContextSnapshot", null=True, blank=True, on_delete=models.SET_NULL)
    revision = models.PositiveIntegerField(default=1)
    next_round_index = models.PositiveIntegerField(default=0)
    tool_steps = models.PositiveIntegerField(default=0)
    transcript = models.JSONField(default=list)
    checkpoint_boundary = models.CharField(max_length=32, default="round")
    tool_manifest_hash = models.CharField(max_length=64, blank=True, default="")
    context_hash = models.CharField(max_length=64, blank=True, default="")
    transcript_hash = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.READY)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_sync_ai_agent_checkpoint"
        indexes = [models.Index(fields=["run", "status"], name="idx_ai_checkpoint_run_status")]


class ChatPendingInteraction(models.Model):
    class Kind(models.TextChoices):
        ASK_USER = "ask_user", "Ask user"
        CLIENT_TOOL = "client_tool", "Client tool"
        CONSENT = "consent", "Consent"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CLAIMED = "claimed", "Claimed"
        RESOLVED = "resolved", "Resolved"
        REFUSED = "refused", "Refused"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    run = models.ForeignKey("chat_sync.ChatRun", on_delete=models.CASCADE, related_name="pending_interactions")
    tool_call = models.OneToOneField(ChatToolCall, on_delete=models.CASCADE, related_name="interaction")
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    schema_version = models.PositiveIntegerField(default=1)
    interaction_key = models.CharField(max_length=192, unique=True, db_index=True, default="")
    request_hash = models.CharField(max_length=64, default="")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    request_schema = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    required_platform = models.CharField(max_length=32, blank=True, default="")
    required_capability = models.CharField(max_length=64, blank=True, default="")
    tool_version = models.CharField(max_length=64, blank=True, default="")
    claimed_by_device = models.CharField(max_length=255, blank=True, default="")
    claim_token_hash = models.CharField(max_length=128, blank=True, default="")
    claim_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    response = models.JSONField(null=True, blank=True)
    response_hash = models.CharField(max_length=64, blank=True, default="")
    result_summary = models.TextField(blank=True, default="")
    result_ref = models.CharField(max_length=512, blank=True, default="")
    last_error_code = models.CharField(max_length=64, blank=True, default="")
    response_idempotency_key = models.CharField(max_length=128, null=True, blank=True)
    responded_by_device = models.CharField(max_length=128, blank=True, default="")
    response_received_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_sync_ai_pending_interaction"
        constraints = [
            models.UniqueConstraint(
                fields=["run", "response_idempotency_key"],
                name="uniq_ai_interaction_response_key",
            )
        ]
        indexes = [
            models.Index(fields=["run", "status"], name="idx_ai_interaction_run_status"),
            models.Index(fields=["status", "claim_expires_at"], name="idx_ai_interaction_claim"),
            models.Index(fields=["required_platform", "status"], name="idx_ai_interaction_platform"),
        ]
