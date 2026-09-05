from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from hospital_care.models.conversations import ClinicalConversationBinding


class Consultation(models.Model):
    """线上问诊单（DOCTOR-WORKSPACE-000004 页面形态修订）。

    患者客户端独立提交一次线上问诊创建一条问诊单；只有存在问诊单的患者
    才进入医生“线上问诊”工作台。消息、接管、结束等状态机复用关联的
    ClinicalConversationBinding / ChatThread 体系，问诊单只承载提交数据。
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    binding = models.OneToOneField(
        ClinicalConversationBinding,
        related_name="consultation",
        on_delete=models.PROTECT,
        db_constraint=False,
    )
    # 问诊编号：C + 提交日期 + 当日 4 位序列（如 C202505140032）。
    consult_no = models.CharField(max_length=24, unique=True)
    consult_date = models.DateField()
    daily_seq = models.IntegerField()
    member_id = models.IntegerField()
    chief_complaint = models.TextField(blank=True, default="")
    # 问诊材料（患者客户端提交）：补充病史与开单项目均为选填。
    past_history = models.TextField(blank=True, default="")
    family_history = models.TextField(blank=True, default="")
    allergy_history = models.TextField(blank=True, default="")
    order_items = models.JSONField(default=list, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="hospital_consultations",
        on_delete=models.PROTECT,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["consult_date", "daily_seq"], name="uniq_consultation_date_seq"),
        ]
        indexes = [
            models.Index(fields=["member_id", "submitted_at"], name="idx_consultation_member_time"),
            models.Index(fields=["submitted_at"], name="idx_consultation_submitted"),
        ]

    def __str__(self) -> str:  # pragma: no cover - 调试展示
        return f"Consultation({self.consult_no})"
