from __future__ import annotations

from rest_framework import serializers


class CreateRunSerializer(serializers.Serializer):
    client_message_id = serializers.UUIDField()
    content = serializers.CharField(required=False, allow_blank=True, max_length=12000)
    capability = serializers.CharField(required=False, default="chat", max_length=64)
    preferences_revision = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    context_parent_message_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    references = serializers.ListField(required=False, default=list)
    attachments = serializers.ListField(required=False, default=list)
    client = serializers.DictField(required=False, default=dict)
    capability_config = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        content = (attrs.get("content") or "").strip()
        attrs["content"] = content
        if not content and not attrs.get("references") and not attrs.get("attachments"):
            raise serializers.ValidationError({"content": "content_or_reference_required"})
        if len(attrs.get("capability_config") or {}) > 32:
            raise serializers.ValidationError({"capability_config": "too_many_properties"})
        if len(attrs.get("references") or []) + len(attrs.get("attachments") or []) > 16:
            raise serializers.ValidationError({"references": "too_many_context_items"})
        for item in attrs.get("references") or []:
            if not isinstance(item, dict) or item.get("type") not in {"health_resource", "knowledge_chunk"}:
                raise serializers.ValidationError({"references": "invalid_reference"})
        for item in attrs.get("attachments") or []:
            if not isinstance(item, dict) or not item.get("file_id"):
                raise serializers.ValidationError({"attachments": "invalid_attachment"})
        client = attrs.get("client") or {}
        for key, limit in (("platform", 32), ("version", 64), ("device_id", 128)):
            value = client.get(key, "")
            if not isinstance(value, str) or len(value) > limit or any(ord(char) < 32 for char in value):
                raise serializers.ValidationError({"client": f"invalid_{key}"})
        tools = client.get("client_tools", [])
        if not isinstance(tools, list) or len(tools) > 32:
            raise serializers.ValidationError({"client": "invalid_client_tools"})
        for item in tools:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str) or len(item["name"]) > 128:
                raise serializers.ValidationError({"client": "invalid_client_tool"})
            if item.get("version") is not None and (not isinstance(item.get("version"), str) or len(item["version"]) > 64):
                raise serializers.ValidationError({"client": "invalid_client_tool_version"})
        return attrs


class PreferencesSerializer(serializers.Serializer):
    revision = serializers.IntegerField(read_only=True)
    capability = serializers.ChoiceField(choices=["chat"], required=False)
    enabled_tools = serializers.ListField(child=serializers.CharField(max_length=64), required=False)
    knowledge_bases = serializers.ListField(child=serializers.CharField(max_length=128), required=False)
    subagent = serializers.DictField(required=False)
    persona = serializers.DictField(required=False)
    llm_selection = serializers.DictField(required=False)
    language = serializers.CharField(max_length=32, required=False, allow_blank=True)
    voice_preferences = serializers.DictField(required=False)

    def validate_language(self, value):
        if value and value.lower().split("-")[0] not in {"zh", "en"}:
            raise serializers.ValidationError("unsupported_language")
        return value


class ContextSummarySourceSerializer(serializers.Serializer):
    source_id = serializers.CharField(max_length=255)
    type = serializers.CharField(max_length=64)
    title = serializers.CharField(max_length=255, allow_blank=True)
    availability = serializers.ChoiceField(choices=["available", "metadata_only", "unavailable"])


class ContextSummarySerializer(serializers.Serializer):
    run_id = serializers.UUIDField()
    build_status = serializers.ChoiceField(choices=["pending", "building", "ready", "degraded", "failed"])
    preferences_revision = serializers.IntegerField(allow_null=True)
    language = serializers.CharField(max_length=32)
    history = serializers.DictField()
    budget_level = serializers.ChoiceField(choices=["normal", "near_limit", "exceeded"])
    sources = ContextSummarySourceSerializer(many=True)


class RunResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    thread_id = serializers.UUIDField()
    status = serializers.CharField()
    capability = serializers.CharField()
    capability_version = serializers.CharField()
    user_message_id = serializers.IntegerField()
    assistant_message_id = serializers.IntegerField()
    last_sequence = serializers.IntegerField(min_value=0)
    error = serializers.JSONField(allow_null=True)
    created_at = serializers.DateTimeField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)


class InteractionResponseSerializer(serializers.Serializer):
    response = serializers.DictField()
    device_id = serializers.CharField(required=False, allow_blank=True, max_length=255)
    claim_token = serializers.CharField(required=False, allow_blank=True, max_length=512)


class InteractionClaimSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=255)
    platform = serializers.CharField(max_length=32)
    version = serializers.CharField(required=False, allow_blank=True, max_length=64)


class InteractionHeartbeatSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=255)
    claim_token = serializers.CharField(max_length=512)


class InteractionRefuseSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=128)
    device_id = serializers.CharField(required=False, allow_blank=True, max_length=255)
    claim_token = serializers.CharField(required=False, allow_blank=True, max_length=512)


class DeferredToolLoadSerializer(serializers.Serializer):
    run_id = serializers.UUIDField()
    names = serializers.ListField(child=serializers.CharField(max_length=64), min_length=1, max_length=8)


class DeferredToolRevokeSerializer(serializers.Serializer):
    names = serializers.ListField(child=serializers.CharField(max_length=64), min_length=1, max_length=8)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=128)
