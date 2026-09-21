from __future__ import annotations

import uuid

from django.db import models


class HospitalAITriageBinding(models.Model):
    """医院 AI 导诊会话绑定（无具体医生智能体，使用 ai_triage 场景模型）。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.OneToOneField(
        "chat_sync.ChatThread",
        related_name="hospital_ai_triage_binding",
        on_delete=models.PROTECT,
        db_constraint=False,
    )
    hospital = models.ForeignKey(
        "hospital_care.Hospital",
        related_name="ai_triage_bindings",
        on_delete=models.PROTECT,
    )
    scenario_binding = models.ForeignKey(
        "ai_config.AIScenarioModelBinding",
        related_name="hospital_ai_triage_bindings",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["hospital", "updated_at"], name="idx_triage_hospital_updated"),
        ]
