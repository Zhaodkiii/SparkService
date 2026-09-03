from __future__ import annotations

import uuid

from django.db import models

from hospital_care.models.organization import DoctorProfile, Hospital


class DoctorPatientSummary(models.Model):
    """DOCTOR-WORKSPACE-000001 D-020~D-023：患者工作台 AI 总结（系统生成、只读、可追溯）。

    - 按（doctor, member）维度保存生成快照；新版本 version 递增。
    - 四个分区：当前问题/服务概况、关键健康信息、会话要点、待跟进事项。
    - input_snapshot 记录生成时的患者/医生/医院/会话集合/资料时间与工具版本。
    """

    class Status(models.TextChoices):
        READY = "ready"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hospital = models.ForeignKey(Hospital, related_name="patient_summaries", on_delete=models.PROTECT)
    doctor = models.ForeignKey(DoctorProfile, related_name="patient_summaries", on_delete=models.PROTECT)
    member_id = models.IntegerField(db_index=True)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.READY)
    current_issues = models.TextField(blank=True, default="", db_comment="当前问题/服务概况")
    key_health_info = models.TextField(blank=True, default="", db_comment="关键健康信息")
    conversation_highlights = models.TextField(blank=True, default="", db_comment="会话要点")
    follow_up_items = models.JSONField(default=list, blank=True, db_comment="待跟进事项")
    input_snapshot = models.JSONField(default=dict, blank=True, db_comment="生成输入快照：会话集合、资料时间、工具版本")
    tool_name = models.CharField(max_length=64, default="patient-workspace-summary-v1")
    failure_reason = models.CharField(max_length=255, blank=True, default="")
    generated_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["doctor", "member_id", "version"], name="uniq_patient_summary_version"),
        ]
        indexes = [
            models.Index(fields=["doctor", "member_id", "-generated_at"], name="idx_patient_summary_latest"),
        ]


class DoctorPatientSummaryAck(models.Model):
    """D-023：医生对某一总结版本的“已了解”确认记录；不改变总结正文。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    summary = models.ForeignKey(DoctorPatientSummary, related_name="acks", on_delete=models.CASCADE)
    doctor = models.ForeignKey(DoctorProfile, related_name="patient_summary_acks", on_delete=models.PROTECT)
    acknowledged = models.BooleanField(default=True)
    acted_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["summary", "doctor"], name="uniq_patient_summary_ack"),
        ]
