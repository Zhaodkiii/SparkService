from __future__ import annotations

from chat_sync.ai_runtime.protocols.tool_protocol import BaseTool, ToolDefinition, ToolResult

from ._common import context_or_error, safe_text


class HealthSourcesTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_member_health_sources",
            description="列出当前成员可读取的健康资料目录。",
            raw_parameters={
                "type": "object",
                "properties": {
                    "resource_types": {"type": "array", "items": {"type": "string", "maxLength": 64}, "maxItems": 8},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": [],
                "additionalProperties": False,
            },
        )

    async def execute(self, *, resource_types=None, limit=10, _execution_context=None, **kwargs) -> ToolResult:
        context, error = context_or_error(_execution_context)
        if error:
            return error
        from django.contrib.auth import get_user_model
        from medical.services.member_binding_service import get_active_binding

        user = get_user_model().objects.get(pk=context.user_id)
        if get_active_binding(user=user, member_id=context.member_id) is None:
            return ToolResult(content="健康资料不可用或无权访问。", success=False, metadata={"error_code": "tool_permission_denied"})
        from medical.models import HealthExamReport, ExaminationReport, MedicalCase, MedicationPlan

        model_map = {
            "health_exam_report": HealthExamReport,
            "examination_report": ExaminationReport,
            "medical_case": MedicalCase,
            "medication_plan": MedicationPlan,
        }
        types = [str(item) for item in (resource_types or model_map)]
        rows: list[str] = []
        sources: list[dict[str, str]] = []
        for resource_type in types:
            model = model_map.get(resource_type)
            if model is None:
                continue
            for item in model.objects.filter(member_id=context.member_id, is_deleted=False).order_by("-updated_at", "-id")[: max(1, min(int(limit), 20))]:
                title = getattr(item, "title", None) or getattr(item, "summary", None) or getattr(item, "drug_name", None) or resource_type
                rows.append(f"{resource_type}:{item.id} | {safe_text(title, 160)} | updated_at={item.updated_at.isoformat()}")
                sources.append({"source_id": f"{resource_type}:{item.id}", "type": resource_type})
        return ToolResult(content="\n".join(rows) or "没有可用健康资料。", sources=sources)
