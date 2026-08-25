from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class RunStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    WAITING_FOR_USER_INPUT = "waiting_for_user_input", "Waiting for user input"
    WAITING_FOR_CLIENT_TOOL = "waiting_for_client_tool", "Waiting for client tool"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    INTERRUPTED = "interrupted", "Interrupted"


TERMINAL_RUN_STATUSES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.INTERRUPTED,
    }
)

ALLOWED_RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.FAILED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.WAITING_FOR_USER_INPUT,
            RunStatus.WAITING_FOR_CLIENT_TOOL,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.INTERRUPTED,
        }
    ),
    RunStatus.WAITING_FOR_USER_INPUT: frozenset({RunStatus.QUEUED, RunStatus.FAILED, RunStatus.CANCELLED}),
    RunStatus.WAITING_FOR_CLIENT_TOOL: frozenset({RunStatus.QUEUED, RunStatus.FAILED, RunStatus.CANCELLED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
    RunStatus.INTERRUPTED: frozenset(),
}


def assert_run_transition(current: str, target: str) -> None:
    if target not in ALLOWED_RUN_TRANSITIONS.get(current, frozenset()):
        raise ValueError(f"invalid chat run transition: {current}->{target}")


class ChatRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_ai_runs")
    thread = models.ForeignKey("chat_sync.ChatThread", on_delete=models.CASCADE, related_name="ai_runs")
    user_message = models.ForeignKey(
        "chat_sync.ChatMessage",
        on_delete=models.RESTRICT,
        related_name="ai_user_runs",
    )
    assistant_message = models.ForeignKey(
        "chat_sync.ChatMessage",
        on_delete=models.RESTRICT,
        related_name="ai_assistant_runs",
    )
    context_parent_message = models.ForeignKey(
        "chat_sync.ChatMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_context_child_runs",
    )
    status = models.CharField(max_length=32, choices=RunStatus.choices, default=RunStatus.QUEUED, db_index=True)
    capability = models.CharField(max_length=64, default="chat")
    capability_version = models.CharField(max_length=64, default="v1")
    provider = models.CharField(max_length=128, blank=True, default="")
    model = models.CharField(max_length=128, blank=True, default="")
    model_config_version = models.CharField(max_length=64, blank=True, default="")
    idempotency_key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    request_snapshot = models.JSONField(default=dict)
    last_sequence = models.PositiveBigIntegerField(default=0)
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    lease_owner = models.CharField(max_length=128, blank=True, default="")
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(null=True, blank=True)
    first_token_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    finish_reason = models.CharField(max_length=64, blank=True, default="")
    provider_request_id = models.CharField(max_length=128, blank=True, default="")
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    retryable = models.BooleanField(default=False)
    regenerated_from_run = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="regenerated_runs",
    )
    regenerated_from_message = models.ForeignKey(
        "chat_sync.ChatMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="regenerated_ai_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_sync_ai_run"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "idempotency_key"], name="uniq_ai_run_user_idempotency"),
            models.UniqueConstraint(fields=["assistant_message"], name="uniq_ai_run_assistant_message"),
            models.CheckConstraint(condition=models.Q(max_attempts__gte=1), name="ai_run_max_attempts_gte_1"),
            models.CheckConstraint(condition=models.Q(last_sequence__gte=0), name="ai_run_sequence_gte_0"),
        ]
        indexes = [
            models.Index(fields=["thread", "status", "created_at"], name="idx_ai_run_thread_status_time"),
            models.Index(fields=["user", "created_at"], name="idx_ai_run_user_time"),
            models.Index(fields=["status", "lease_expires_at"], name="idx_ai_run_status_lease"),
        ]

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_RUN_STATUSES


class ChatThreadRunLock(models.Model):
    thread = models.OneToOneField(
        "chat_sync.ChatThread",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="ai_run_lock",
    )
    active_run = models.OneToOneField(
        ChatRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_thread_lock",
    )
    generation = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_sync_ai_thread_run_lock"


class ChatWebSocketTicket(models.Model):
    """Single-use, short-lived browser credential for the Run WebSocket."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_ws_tickets")
    token_hash = models.CharField(max_length=64, unique=True)
    websocket_path = models.CharField(max_length=128, default="/ws/chat/runs/")
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_sync_ai_ws_ticket"
        indexes = [models.Index(fields=["expires_at", "used_at"], name="idx_ai_ws_ticket_expiry")]
