from rest_framework import serializers

from chat_sync.models import ChatMessage


class ChatRemoteMessageSerializer(serializers.Serializer):
    thread_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=ChatMessage.Role.choices)
    kind = serializers.ChoiceField(choices=ChatMessage.Kind.choices)
    content = serializers.CharField(allow_blank=True)
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


class ChatThreadDeleteRequestSerializer(serializers.Serializer):
    thread_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
