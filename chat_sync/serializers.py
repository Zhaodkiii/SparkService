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


class ChatPushRequestSerializer(serializers.Serializer):
    messages = ChatRemoteMessageSerializer(many=True)
