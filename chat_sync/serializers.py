from rest_framework import serializers

from chat_sync.models import ChatMessage, ChatThread


class ChatRemoteThreadSerializer(serializers.Serializer):
    thread_id = serializers.UUIDField()
    title = serializers.CharField(allow_blank=True)
    scenario = serializers.ChoiceField(choices=ChatThread.Scenario.choices)
    patient_id = serializers.UUIDField(required=False, allow_null=True)
    member_id = serializers.IntegerField(required=False, allow_null=True)
    is_deleted = serializers.BooleanField(required=False, default=False)
    deleted_at = serializers.DateTimeField(required=False, allow_null=True)
    updated_at = serializers.DateTimeField(required=False)
    server_updated_at = serializers.DateTimeField(required=False)
    image_delivery_mode = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    current_model_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    temperature = serializers.FloatField(required=False, allow_null=True)
    top_p = serializers.FloatField(required=False, allow_null=True)
    max_tokens = serializers.IntegerField(required=False, allow_null=True)
    max_messages = serializers.IntegerField(required=False, allow_null=True)
    role_prompt = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ChatRemoteMessageSerializer(serializers.Serializer):
    thread_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=ChatMessage.Role.choices)
    kind = serializers.ChoiceField(choices=ChatMessage.Kind.choices)
    content = serializers.CharField(allow_blank=True)
    model_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    client_message_id = serializers.UUIDField()
    server_message_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    delivery_state = serializers.ChoiceField(choices=ChatMessage.DeliveryState.choices)
    created_at = serializers.DateTimeField()
    server_updated_at = serializers.DateTimeField(required=False, allow_null=True)
    tombstone = serializers.BooleanField(required=False, default=False)
    thread_current_model_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    thread_temperature = serializers.FloatField(required=False, allow_null=True)
    thread_top_p = serializers.FloatField(required=False, allow_null=True)
    thread_max_tokens = serializers.IntegerField(required=False, allow_null=True)
    thread_max_messages = serializers.IntegerField(required=False, allow_null=True)
    thread_role_prompt = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    attachments = serializers.JSONField(required=False)
    reasoning_content = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    reasoning_duration_ms = serializers.IntegerField(required=False, allow_null=True)
    reasoning_expanded = serializers.BooleanField(required=False)
    reasoning_visibility = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ChatPushRequestSerializer(serializers.Serializer):
    messages = ChatRemoteMessageSerializer(many=True)


class ChatThreadPushRequestSerializer(serializers.Serializer):
    threads = ChatRemoteThreadSerializer(many=True)


class ChatThreadDeleteRequestSerializer(serializers.Serializer):
    thread_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
