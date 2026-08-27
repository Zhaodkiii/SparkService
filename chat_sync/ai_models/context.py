from __future__ import annotations

from django.db import models


class ChatThreadPreferences(models.Model):
    thread = models.OneToOneField("chat_sync.ChatThread", on_delete=models.CASCADE, related_name="ai_preferences")
    active_head_message = models.ForeignKey(
        "chat_sync.ChatMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_active_preference_heads",
    )
    revision = models.PositiveIntegerField(default=1)
    capability = models.CharField(max_length=64, default="chat")
    enabled_tools = models.JSONField(default=list, blank=True)
    knowledge_bases = models.JSONField(default=list, blank=True)
    subagent = models.JSONField(default=dict, blank=True)
    persona = models.JSONField(default=dict, blank=True)
    llm_selection = models.JSONField(default=dict, blank=True)
    language = models.CharField(max_length=32, blank=True, default="")
    voice_preferences = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_sync_ai_thread_preferences"


class ChatTurnContextSnapshot(models.Model):
    run = models.OneToOneField("chat_sync.ChatRun", on_delete=models.CASCADE, related_name="context_snapshot")
    schema_version = models.PositiveSmallIntegerField(default=1)
    prompt_version = models.CharField(max_length=64, default="chat.prompt.v1")
    language = models.CharField(max_length=32, blank=True, default="zh-CN")
    preferences_revision = models.PositiveIntegerField(null=True, blank=True)
    history_head_message_id = models.BigIntegerField(null=True, blank=True)
    selected_message_ids = models.JSONField(default=list, blank=True)
    history_summary = models.TextField(blank=True, default="")
    summary_up_to_message_id = models.BigIntegerField(null=True, blank=True)
    route_snapshot = models.JSONField(default=dict, blank=True)
    build_status = models.CharField(max_length=16, default="ready")
    built_at = models.DateTimeField(null=True, blank=True)
    sources = models.JSONField(default=list, blank=True)
    tool_manifest = models.JSONField(default=list, blank=True)
    tool_manifest_source = models.JSONField(default=list, blank=True)
    tool_manifest_filtered = models.JSONField(default=list, blank=True)
    tool_manifest_hash = models.CharField(max_length=64, blank=True, default="")
    token_budget = models.JSONField(default=dict, blank=True)
    trim_trace = models.JSONField(default=list, blank=True)
    snapshot_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_sync_ai_turn_context_snapshot"


class ChatDeferredToolState(models.Model):
    thread = models.ForeignKey("chat_sync.ChatThread", on_delete=models.CASCADE, related_name="ai_deferred_tools")
    provider_key = models.CharField(max_length=128, blank=True, default="")
    tool_name = models.CharField(max_length=128)
    schema_version = models.CharField(max_length=64, default="v1")
    schema_hash = models.CharField(max_length=64, blank=True, default="")
    capability = models.CharField(max_length=64, blank=True, default="")
    capability_version = models.CharField(max_length=64, blank=True, default="")
    loaded_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=128, blank=True, default="")
    last_loaded_run = models.ForeignKey(
        "chat_sync.ChatRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deferred_tool_loads",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_sync_ai_deferred_tool_state"
        constraints = [
            models.UniqueConstraint(
                fields=["thread", "provider_key", "tool_name"],
                name="uniq_ai_deferred_thread_provider_tool",
            )
        ]
