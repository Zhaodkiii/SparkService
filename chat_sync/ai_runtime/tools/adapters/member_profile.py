from __future__ import annotations

from chat_sync.ai_runtime.protocols.tool_protocol import BaseTool, ToolDefinition, ToolResult

from ._common import context_or_error, safe_text


class MemberProfileTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="query_member_profile",
            description="读取当前成员被授权的结构化健康资料摘要。",
            raw_parameters={
                "type": "object",
                "properties": {"sections": {"type": "array", "items": {"type": "string", "maxLength": 32}, "maxItems": 8}},
                "required": [],
                "additionalProperties": False,
            },
        )

    async def execute(self, *, sections=None, _execution_context=None, **kwargs) -> ToolResult:
        context, error = context_or_error(_execution_context)
        if error:
            return error
        from django.contrib.auth import get_user_model
        from medical.models import Member, MemberMedicalProfile
        from medical.services.member_binding_service import get_active_binding

        user = get_user_model().objects.get(pk=context.user_id)
        if get_active_binding(user=user, member_id=context.member_id) is None:
            return ToolResult(content="成员资料不可用或无权访问。", success=False, metadata={"error_code": "tool_permission_denied"})
        member = Member.objects.filter(pk=context.member_id, is_deleted=False).first()
        if member is None:
            return ToolResult(content="成员资料不可用。", success=False, metadata={"error_code": "tool_resource_not_found"})
        profile = MemberMedicalProfile.objects.filter(member_id=context.member_id, user=user, is_deleted=False).first()
        wanted = {str(item) for item in (sections or [])}
        fields: list[str] = []
        if not wanted or "allergies" in wanted:
            fields.append(f"allergies: {safe_text(member.allergies, 800)}")
        if not wanted or "chronic_conditions" in wanted:
            values = profile.chronic_conditions if profile else member.chronic_conditions
            fields.append(f"chronic_conditions: {safe_text(values, 800)}")
        if not wanted or "medication_focus" in wanted:
            fields.append(f"medication_focus: {safe_text(profile.medication_focus if profile else [], 800)}")
        if not fields:
            return ToolResult(content="没有请求的资料分区。", success=False, metadata={"error_code": "tool_arguments_schema_invalid"})
        return ToolResult(content="\n".join(fields), sources=[{"source_id": f"member_profile:{context.member_id}", "type": "member_profile"}])
