from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


class ChatRunEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    run = models.ForeignKey("chat_sync.ChatRun", on_delete=models.CASCADE, related_name="events")
    sequence = models.PositiveBigIntegerField()
    type = models.CharField(max_length=64)
    payload_version = models.PositiveIntegerField(default=1)
    payload = models.JSONField(default=dict)
    terminal_marker = models.CharField(max_length=16, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_sync_ai_run_event"
        ordering = ["sequence", "id"]
        constraints = [
            models.UniqueConstraint(fields=["run", "sequence"], name="uniq_ai_event_run_sequence"),
            models.UniqueConstraint(fields=["run", "terminal_marker"], name="uniq_ai_event_terminal_marker"),
        ]
        indexes = [models.Index(fields=["run", "sequence"], name="idx_ai_event_run_sequence")]


class ChatEventOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    event = models.OneToOneField(ChatRunEvent, on_delete=models.CASCADE, related_name="outbox")
    channel_group = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(null=True, blank=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    lock_owner = models.CharField(max_length=128, blank=True, default="")
    locked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_sync_ai_event_outbox"
        indexes = [models.Index(fields=["status", "available_at"], name="idx_ai_outbox_status_time")]


class ChatUsageRecord(models.Model):
    run = models.OneToOneField("chat_sync.ChatRun", on_delete=models.CASCADE, related_name="usage")
    provider = models.CharField(max_length=128, blank=True, default="")
    model = models.CharField(max_length=128, blank=True, default="")
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    reasoning_tokens = models.PositiveIntegerField(default=0)
    tool_calls = models.PositiveIntegerField(default=0)
    price_version = models.CharField(max_length=64, blank=True, default="")
    amount = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("0"))
    currency = models.CharField(max_length=8, default="USD")
    usage_source = models.CharField(max_length=16, default="unavailable")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_sync_ai_usage_record"
        indexes = [models.Index(fields=["provider", "created_at"], name="idx_ai_usage_provider_time")]
