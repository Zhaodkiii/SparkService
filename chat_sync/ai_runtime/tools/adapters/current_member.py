from __future__ import annotations

from chat_sync.ai_runtime.protocols.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult

from ._common import context_or_error, safe_text


class CurrentMemberTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_current_member",
            description="读取当前对话成员的最小身份资料。",
            raw_parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        )

    async def execute(self, *, _execution_context=None, **kwargs) -> ToolResult:
        context, error = context_or_error(_execution_context)
        if error:
            return error
        from medical.models import Member
        from medical.services.member_binding_service import get_active_binding

        # The service accepts a User object; the executor supplies only a stable
        # user id so the adapter resolves it at the final authorization gate.
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.get(pk=context.user_id)
        if get_active_binding(user=user, member_id=context.member_id) is None:
            return ToolResult(content="成员资料不可用或无权访问。", success=False, metadata={"error_code": "tool_permission_denied"})
        member = Member.objects.filter(pk=context.member_id, is_deleted=False).first()
        if member is None:
            return ToolResult(content="成员资料不可用。", success=False, metadata={"error_code": "tool_resource_not_found"})
        return ToolResult(
            content=(
                f"member_id: {member.id}\nname: {safe_text(member.name, 64)}\n"
                f"gender: {safe_text(member.gender, 16)}\n"
                f"birth_date: {member.birth_date.isoformat() if member.birth_date else ''}"
            ),
            sources=[{"source_id": f"member:{member.id}", "type": "member"}],
        )
