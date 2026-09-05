from rest_framework import serializers

from hospital_care.models import ClinicalConversationBinding, ConversationEndReason


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
    # DOCTOR-WORKSPACE-000004：优先使用固定枚举；end_reason 文本仅作旧客户端兼容。
    end_reason_code = serializers.ChoiceField(choices=ConversationEndReason.choices, required=False)
    end_reason_note = serializers.CharField(required=False, allow_blank=True, default="")
    end_reason = serializers.CharField(required=False, allow_blank=True, default="")


class ConversationRiskUpdateSerializer(serializers.Serializer):
    risk_signal_level = serializers.ChoiceField(choices=ClinicalConversationBinding.RiskSignalLevel.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    version = serializers.IntegerField()


class ReadCursorUpdateSerializer(serializers.Serializer):
    last_read_message_id = serializers.IntegerField(required=False, min_value=0)


class DoctorMessageSerializer(serializers.Serializer):
    # 允许空文本：医生可以只发附件（attachments），由 service 层保证两者至少其一
    text = serializers.CharField(required=False, allow_blank=True, default="")
    version = serializers.IntegerField(required=False)
    attachments = serializers.ListField(child=serializers.DictField(), required=False, max_length=5)


class PatientSummaryAckSerializer(serializers.Serializer):
    acknowledged = serializers.BooleanField()
