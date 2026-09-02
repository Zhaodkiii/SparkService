from rest_framework import serializers

from hospital_care.models import ClinicalConversationBinding


class DoctorAgentUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True)
    public_summary = serializers.CharField(required=False, allow_blank=True)
    greeting = serializers.CharField(required=False, allow_blank=True)
    service_boundary = serializers.CharField(required=False, allow_blank=True)
    department_id = serializers.UUIDField(required=False)
    scenario_binding_id = serializers.IntegerField(required=False)
    version = serializers.IntegerField(required=False)


class DoctorAgentSubmitSerializer(serializers.Serializer):
    version = serializers.IntegerField()


class AttentionUpdateSerializer(serializers.Serializer):
    doctor_attention_level = serializers.ChoiceField(choices=ClinicalConversationBinding.AttentionLevel.choices)
    attention_note = serializers.CharField(required=False, allow_blank=True)
    version = serializers.IntegerField()


class ConversationVersionSerializer(serializers.Serializer):
    version = serializers.IntegerField()


class ConversationEndSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    end_reason = serializers.CharField()


class DoctorMessageSerializer(serializers.Serializer):
    text = serializers.CharField()
    version = serializers.IntegerField(required=False)
