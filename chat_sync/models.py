import uuid

from django.conf import settings
from django.db import models


class ChatThread(models.Model):
    class Scenario(models.TextChoices):
        CHAT = "chat"

    class ImageDeliveryMode(models.TextChoices):
        DIRECT_MULTIMODAL = "directMultimodal"
        LOCAL_OCR = "localOCR"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="chat_threads", on_delete=models.CASCADE)
    patient_id = models.UUIDField(null=True, blank=True, db_index=True)
    member_id = models.IntegerField(null=True, blank=True, db_index=True)
    title = models.CharField(max_length=255, default="New Chat")
    scenario = models.CharField(max_length=32, choices=Scenario.choices, default=Scenario.CHAT)
    current_model_name = models.CharField(max_length=128, blank=True, default="")
    temperature = models.FloatField(null=True, blank=True)
    top_p = models.FloatField(default=1.0)
    max_tokens = models.IntegerField(null=True, blank=True)
    max_messages = models.IntegerField(default=20)
    role_prompt = models.TextField(blank=True, default="")
    image_delivery_mode = models.CharField(
        max_length=32,
        choices=ImageDeliveryMode.choices,
        null=True,
        blank=True,
        db_index=True,
    )
    icon_name = models.CharField(max_length=128, blank=True, default="")
    icon_color_name = models.CharField(max_length=64, blank=True, default="")
    is_pinned = models.BooleanField(default=False, db_index=True)
    pinned_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    server_updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "id"], name="uniq_chat_thread_user_thread"),
        ]

    @property
    def system_prompt(self) -> str:
        return self.role_prompt or ""

    @system_prompt.setter
    def system_prompt(self, value: str | None) -> None:
        self.role_prompt = value or ""


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        SYSTEM = "system"
        USER = "user"
        ASSISTANT = "assistant"

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
    model_name = models.CharField(max_length=128, blank=True, default="")
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
            models.Index(fields=["user", "role", "-created_at", "-id"], name="idx_chat_msg_user_role_time"),
            models.Index(fields=["user", "-created_at", "-id"], name="idx_chat_msg_user_time"),
        ]


class ChatMessageBlock(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        STREAMING = "streaming"
        READY = "ready"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="chat_message_blocks", on_delete=models.CASCADE)
    thread = models.ForeignKey(ChatThread, related_name="message_blocks", on_delete=models.CASCADE)
    message = models.ForeignKey(ChatMessage, related_name="blocks", on_delete=models.CASCADE)
    kind = models.CharField(max_length=64, default="text", db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.READY)
    revision = models.BigIntegerField(default=0)
    order_key = models.FloatField(null=True, blank=True)
    tool_call_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    parent_tool_call_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    parent_block_id = models.UUIDField(null=True, blank=True, db_index=True)
    node_role = models.CharField(max_length=32, default="timeline")
    anchor = models.JSONField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    server_updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["order_key", "created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "id"], name="uniq_chat_block_user_block_id"),
        ]
        indexes = [
            models.Index(fields=["message", "order_key", "created_at"], name="idx_chat_block_msg_order"),
            models.Index(fields=["user", "server_updated_at", "id"], name="idx_chat_block_user_sync"),
        ]
