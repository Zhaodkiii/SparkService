from rest_framework import serializers

from hospital_care.models import Hospital


class CreateConversationSerializer(serializers.Serializer):
    agent_id = serializers.UUIDField()
    member_id = serializers.IntegerField()
    thread_id = serializers.UUIDField(required=False)


class AppointmentRedirectSerializer(serializers.Serializer):
    hospital_id = serializers.UUIDField()
    member_id = serializers.IntegerField()


class HospitalIdSerializer(serializers.Serializer):
    service_mode = serializers.ChoiceField(choices=Hospital.ServiceMode.choices, required=False)
