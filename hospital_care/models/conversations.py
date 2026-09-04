from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from hospital_care.models.agent_profiles import ClinicalAgentProfile
from hospital_care.models.organization import DoctorProfile, Hospital, HospitalDepartment


class ClinicalConversationBinding(models.Model):
    class ServiceStatus(models.TextChoices):
        AI_ACTIVE = "ai_active"
        PENDING_DOCTOR = "pending_doctor"
        DOCTOR_JOINED = "doctor_joined"
        ENDED = "ended"

    class AttentionLevel(models.TextChoices):
        NORMAL = "normal"
        FOLLOW_UP = "follow_up"
        PRIORITY = "priority"

    class RiskSignalLevel(models.TextChoices):
        NONE = "none"
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.OneToOneField(
        "chat_sync.ChatThread",
        related_name="hospital_binding",
        on_delete=models.PROTECT,
        db_constraint=False,
    )
    hospital = models.ForeignKey(Hospital, related_name="conversation_bindings", on_delete=models.PROTECT)
    department = models.ForeignKey(HospitalDepartment, related_name="conversation_bindings", on_delete=models.PROTECT)
    doctor = models.ForeignKey(DoctorProfile, related_name="conversation_bindings", on_delete=models.PROTECT)
    agent = models.ForeignKey(ClinicalAgentProfile, related_name="conversation_bindings", on_delete=models.PROTECT)
    # CHAT-000058：创建医院会话时服务端按 agent_id 重解析并固定的场景模型绑定快照。
    # 客户端不得提交该字段；历史数据允许为空。
    scenario_binding = models.ForeignKey(
        "ai_config.AIScenarioModelBinding",
        null=True,
        blank=True,
        related_name="conversation_bindings",
        on_delete=models.PROTECT,
    )
    service_status = models.CharField(max_length=32, choices=ServiceStatus.choices, default=ServiceStatus.AI_ACTIVE)
    doctor_attention_level = models.CharField(
        max_length=16,
        choices=AttentionLevel.choices,
        default=AttentionLevel.NORMAL,
    )
    attention_note = models.TextField(blank=True, default="")
    risk_signal_level = models.CharField(
        max_length=16,
        choices=RiskSignalLevel.choices,
        default=RiskSignalLevel.NONE,
    )
    risk_signal_message = models.ForeignKey(
        "chat_sync.ChatMessage",
        null=True,
        blank=True,
        related_name="hospital_risk_bindings",
        on_delete=models.PROTECT,
        db_constraint=False,
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    doctor_joined_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="ended_hospital_conversations",
        on_delete=models.PROTECT,
    )
    end_reason = models.CharField(max_length=64, blank=True, default="")
    version = models.BigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["doctor", "service_status", "doctor_attention_level", "updated_at"],
                name="idx_conv_doctor_queue",
            ),
            models.Index(
                fields=["hospital", "department", "service_status"],
                name="idx_conv_hospital_dept_status",
            ),
        ]


class ChatMessageAttribution(models.Model):
    class ActorType(models.TextChoices):
        PATIENT = "patient"
        AI_AGENT = "ai_agent"
        DOCTOR = "doctor"
        SYSTEM = "system"

    class Source(models.TextChoices):
        PATIENT_APP = "patient_app"
        DOCTOR_CONSOLE = "doctor_console"
        AI_RUNTIME = "ai_runtime"
        SYSTEM = "system"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.OneToOneField(
        "chat_sync.ChatMessage",
        related_name="hospital_attribution",
        on_delete=models.CASCADE,
        db_constraint=False,
    )
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="hospital_message_attributions",
        on_delete=models.PROTECT,
    )
    doctor = models.ForeignKey(
        DoctorProfile,
        null=True,
        blank=True,
        related_name="message_attributions",
        on_delete=models.PROTECT,
    )
    agent = models.ForeignKey(
        ClinicalAgentProfile,
        null=True,
        blank=True,
        related_name="message_attributions",
        on_delete=models.PROTECT,
    )
    display_name_snapshot = models.CharField(max_length=128, blank=True, default="")
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.SYSTEM)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.actor_type == self.ActorType.DOCTOR and (not self.doctor_id or not self.actor_user_id):
            raise ValidationError("doctor attribution requires doctor and actor_user")
        if self.actor_type == self.ActorType.AI_AGENT and not self.agent_id:
            raise ValidationError("ai_agent attribution requires agent")
        if self.actor_type == self.ActorType.PATIENT and self.doctor_id:
            raise ValidationError("patient attribution must not include doctor")


class HospitalCareCommandReceipt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="hospital_care_command_receipts",
        on_delete=models.CASCADE,
    )
    command_key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    resource_type = models.CharField(max_length=64, blank=True, default="")
    resource_id = models.CharField(max_length=64, blank=True, default="")
    response_code = models.IntegerField(default=0)
    response_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["actor_user", "command_key"], name="uniq_hospital_command_receipt"),
        ]
        indexes = [
            models.Index(fields=["actor_user", "created_at"], name="idx_hospital_receipt_user_time"),
        ]
