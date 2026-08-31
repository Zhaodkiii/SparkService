from __future__ import annotations

from rest_framework import serializers

from chat_sync.ai_memory.constants import MAX_CONTENT_CHARS, MAX_MUTATIONS_PER_BATCH, MAX_TITLE_LENGTH

OPERATION_CHOICES = ("create", "update", "confirm", "reject", "delete")


class MemoryEntryWriteSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    title = serializers.CharField(required=False, allow_blank=True, max_length=MAX_TITLE_LENGTH)
    content = serializers.CharField(required=False, allow_blank=False, max_length=MAX_CONTENT_CHARS)
    section_key = serializers.CharField(required=False, allow_blank=True, max_length=64)
    memory_type = serializers.CharField(required=False, allow_blank=True, max_length=32)
    normalized_key = serializers.CharField(required=False, allow_blank=True, max_length=128)
    structured_value = serializers.DictField(required=False)
    is_pinned = serializers.BooleanField(required=False)
    sensitivity = serializers.CharField(required=False, allow_blank=True, max_length=16)
    revision = serializers.IntegerField(required=False)


class MemoryMutationPayloadSerializer(serializers.Serializer):
    scope = serializers.CharField(required=False, allow_blank=True, default="account")
    member_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    agent_key = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    thread_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    layer = serializers.CharField(required=False, allow_blank=True, default="L3")
    document_key = serializers.CharField(required=False, allow_blank=True, default="preferences")
    section_key = serializers.CharField(required=False, allow_blank=True, default="answer_style")
    memory_type = serializers.CharField(required=False, allow_blank=True, default="preference")
    normalized_key = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    title = serializers.CharField(required=False, allow_blank=True, default="", max_length=MAX_TITLE_LENGTH)
    content = serializers.CharField(required=False, allow_blank=True, default="", max_length=MAX_CONTENT_CHARS)
    structured_value = serializers.DictField(required=False)
    is_pinned = serializers.BooleanField(required=False, default=False)
    sort_order = serializers.IntegerField(required=False, default=0)
    source = serializers.CharField(required=False, allow_blank=True, default="user")
    sensitivity = serializers.CharField(required=False, allow_blank=True, default="normal")
    confirmation_status = serializers.CharField(required=False, allow_blank=True, default="not_required")
    status = serializers.CharField(required=False, allow_blank=True, default="active")
    expires_at = serializers.DateTimeField(required=False, allow_null=True, default=None)


class MemoryMutationClientSerializer(serializers.Serializer):
    platform = serializers.CharField(required=False, allow_blank=True, default="")
    version = serializers.CharField(required=False, allow_blank=True, default="")
    device_id = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)


class MemorySyncMutationSerializer(serializers.Serializer):
    mutation_id = serializers.UUIDField()
    memory_id = serializers.UUIDField()
    operation = serializers.ChoiceField(choices=OPERATION_CHOICES)
    base_revision = serializers.IntegerField(required=False, allow_null=True, default=None)
    memory = MemoryMutationPayloadSerializer(required=False)
    client = MemoryMutationClientSerializer(required=False)

    def validate(self, attrs):
        operation = attrs.get("operation")
        if operation == "create" and not attrs.get("memory"):
            raise serializers.ValidationError({"memory": "required for create mutations"})
        return attrs


class MemorySyncPushRequestSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField(required=False, default=1)
    mutations = MemorySyncMutationSerializer(many=True, allow_empty=False)

    def validate_mutations(self, value):
        if len(value) > MAX_MUTATIONS_PER_BATCH:
            raise serializers.ValidationError(f"at most {MAX_MUTATIONS_PER_BATCH} mutations per push batch")
        return value
