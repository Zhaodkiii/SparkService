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
    # DOCTOR-WORKSPACE-000004：结构化结束原因；end_reason 保留展示文本兼容。
    end_reason_code = models.CharField(max_length=32, blank=True, default="")
    end_reason_note = models.TextField(blank=True, default="")
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


class ConversationEndReason(models.TextChoices):
    """DOCTOR-WORKSPACE-000004 第 28 问：固定结束原因枚举；“其他”必须附补充说明。"""

    RESOLVED = "resolved", "已完成咨询"
    OFFLINE_REFERRAL = "offline_referral", "建议线下就诊"
    PATIENT_NO_FOLLOWUP = "patient_no_followup", "患者无继续咨询"
    OTHER = "other", "其他"


class DoctorConversationRiskRevision(models.Model):
    """DOCTOR-WORKSPACE-000004 第 32 问：问诊级医生人工风险调整历史（不可变快照）。

    每次调整新增一条记录；不允许覆盖或删除。当前有效值仍保存在
    ``ClinicalConversationBinding.risk_signal_level``，AI/工具原始结果不被抹除。
    """

    class Source(models.TextChoices):
        DOCTOR_MANUAL = "doctor_manual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    binding = models.ForeignKey(
        ClinicalConversationBinding,
        related_name="risk_revisions",
        on_delete=models.PROTECT,
    )
    doctor = models.ForeignKey(
        DoctorProfile,
        related_name="risk_revisions",
        on_delete=models.PROTECT,
    )
    previous_level = models.CharField(max_length=16, choices=ClinicalConversationBinding.RiskSignalLevel.choices)
    next_level = models.CharField(max_length=16, choices=ClinicalConversationBinding.RiskSignalLevel.choices)
    reason = models.TextField(blank=True, default="")
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.DOCTOR_MANUAL)
    version = models.BigIntegerField(default=1)
    request_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["binding", "created_at", "id"], name="idx_risk_revision_binding_time"),
        ]


class DoctorConversationReadCursor(models.Model):
    """DOCTOR-WORKSPACE-000004 第 31 问：医生-问诊已读游标。

    以 (doctor, thread) 唯一保存最后已读消息 ID；只允许前进，不允许回退。
    问诊级未读数 = 该问诊中游标之后、归属为患者/AI 的可见消息数；
    患者级未读总数 = 当前医生可见未结束问诊的问诊级未读之和。
    """

    id = models.BigAutoField(primary_key=True)
    doctor = models.ForeignKey(
        DoctorProfile,
        related_name="conversation_read_cursors",
        on_delete=models.CASCADE,
    )
    thread = models.ForeignKey(
        "chat_sync.ChatThread",
        related_name="doctor_read_cursors",
        on_delete=models.CASCADE,
        db_constraint=False,
    )
    last_read_message_id = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["doctor", "thread"], name="uniq_doctor_thread_read_cursor"),
        ]
        indexes = [
            models.Index(fields=["doctor", "updated_at"], name="idx_read_cursor_doctor_time"),
        ]


class DoctorPatientAttention(models.Model):
    """DOCTOR-WORKSPACE-000004 第 23 问：医生-患者级“重点患者”标记。

    由当前归属医生手动设置，仅对该医生生效；不影响问诊状态与风险等级。
    同一患者存在多条问诊时以本表为准，避免问诊绑定间标记不一致。
    """

    id = models.BigAutoField(primary_key=True)
    doctor = models.ForeignKey(
        DoctorProfile,
        related_name="patient_attentions",
        on_delete=models.CASCADE,
    )
    member_id = models.IntegerField()
    level = models.CharField(
        max_length=16,
        choices=ClinicalConversationBinding.AttentionLevel.choices,
        default=ClinicalConversationBinding.AttentionLevel.NORMAL,
    )
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["doctor", "member_id"], name="uniq_doctor_patient_attention"),
        ]
        indexes = [
            models.Index(fields=["doctor", "level"], name="idx_patient_attention_level"),
        ]


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
