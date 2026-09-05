from rest_framework import serializers

from hospital_care.models import Hospital


class CreateConversationSerializer(serializers.Serializer):
    agent_id = serializers.UUIDField()
    member_id = serializers.IntegerField()
    thread_id = serializers.UUIDField(required=False)


class SubmitConsultationSerializer(serializers.Serializer):
    """患者客户端独立提交线上问诊（DOCTOR-WORKSPACE-000004 页面形态修订）。"""

    agent_id = serializers.UUIDField()
    member_id = serializers.IntegerField()
    chief_complaint = serializers.CharField(max_length=2000, allow_blank=True, required=False, default="")
    attachments = serializers.ListField(child=serializers.DictField(), required=False, max_length=5)
    # 问诊材料（选填）：开单项目与补充病史。
    order_items = serializers.ListField(child=serializers.CharField(max_length=64), required=False, max_length=8)
    past_history = serializers.CharField(max_length=1000, allow_blank=True, required=False, default="")
    family_history = serializers.CharField(max_length=1000, allow_blank=True, required=False, default="")
    allergy_history = serializers.CharField(max_length=1000, allow_blank=True, required=False, default="")
    thread_id = serializers.UUIDField(required=False)


class AppointmentRedirectSerializer(serializers.Serializer):
    hospital_id = serializers.UUIDField()
    member_id = serializers.IntegerField()


class HospitalIdSerializer(serializers.Serializer):
    service_mode = serializers.ChoiceField(choices=Hospital.ServiceMode.choices, required=False)
