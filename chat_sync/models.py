import uuid

from django.conf import settings
from django.db import models


class ChatThread(models.Model):
    class Scenario(models.TextChoices):
        CHAT = "chat"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="chat_threads", on_delete=models.CASCADE)
    patient_id = models.UUIDField(null=True, blank=True, db_index=True)
    title = models.CharField(max_length=255, default="New Chat")
    scenario = models.CharField(max_length=32, choices=Scenario.choices, default=Scenario.CHAT)
    is_deleted = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    server_updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "id"], name="uniq_chat_thread_user_thread"),
        ]


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        SYSTEM = "system"
        USER = "user"
        ASSISTANT = "assistant"

    class Kind(models.TextChoices):
        TEXT = "text"
        TOOL = "tool"
        CARD = "card"
        SYSTEM = "system"

    class DeliveryState(models.TextChoices):
        PENDING = "pending"
        SENDING = "sending"
        SENT = "sent"
        FAILED = "failed"
        READ = "read"

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="chat_messages", on_delete=models.CASCADE)
    thread = models.ForeignKey(ChatThread, related_name="messages", on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=Role.choices)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.TEXT)
    content = models.TextField(blank=True, default="")
    client_message_id = models.UUIDField(db_index=True)
    server_message_id = models.CharField(max_length=64, db_index=True)
    delivery_state = models.CharField(max_length=16, choices=DeliveryState.choices, default=DeliveryState.SENT)
    tombstone = models.BooleanField(default=False, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(db_index=True)
    server_updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "client_message_id"], name="uniq_chat_message_user_client_id"),
            models.UniqueConstraint(fields=["user", "server_message_id"], name="uniq_chat_message_user_server_id"),
        ]
        indexes = [
            models.Index(fields=["user", "server_updated_at", "id"], name="idx_chat_msg_user_sync"),
            models.Index(fields=["thread", "created_at", "id"], name="idx_chat_msg_thread_created"),
        ]
