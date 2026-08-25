from __future__ import annotations

from chat_sync.ai_runtime.protocols.tool_protocol import BaseTool, ToolDefinition, ToolResult

from ._common import context_or_error, safe_text


class HealthResourceContextTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_health_resource_context",
            description="读取当前成员指定健康资源的安全上下文。",
            raw_parameters={
                "type": "object",
                "properties": {
                    "resource_type": {"type": "string", "enum": ["medical_case", "health_exam_report", "examination_report", "medication_plan"]},
                    "resource_id": {"type": "integer", "minimum": 1},
                },
                "required": ["resource_type", "resource_id"],
                "additionalProperties": False,
            },
        )

    async def execute(self, *, resource_type, resource_id, _execution_context=None, **kwargs) -> ToolResult:
        context, error = context_or_error(_execution_context)
        if error:
            return error
        from django.contrib.auth import get_user_model
        from medical.services.member_binding_service import get_active_binding
        from medical import models as medical_models

        user = get_user_model().objects.get(pk=context.user_id)
        if get_active_binding(user=user, member_id=context.member_id) is None:
            return ToolResult(content="健康资料不可用或无权访问。", success=False, metadata={"error_code": "tool_permission_denied"})
        model_map = {
            "medical_case": medical_models.MedicalCase,
            "health_exam_report": medical_models.HealthExamReport,
            "examination_report": medical_models.ExaminationReport,
            "medication_plan": medical_models.MedicationPlan,
        }
        model = model_map.get(str(resource_type))
        item = model.objects.filter(pk=resource_id, member_id=context.member_id, is_deleted=False).first() if model else None
        if item is None:
            return ToolResult(content="健康资料不可用或无权访问。", success=False, metadata={"error_code": "tool_resource_not_found"})
        fields: list[str] = [f"resource_id: {item.pk}", f"resource_type: {resource_type}"]
        for name in ("title", "record_type", "institution_name", "exam_date", "summary", "diagnosis_summary", "findings", "impression", "drug_name", "frequency_text", "status"):
            value = getattr(item, name, None)
            if value not in (None, ""):
                fields.append(f"{name}: {safe_text(value, 1600)}")
        source_id = f"{resource_type}:{item.pk}"
        return ToolResult(content="\n".join(fields), sources=[{"source_id": source_id, "type": resource_type}])
