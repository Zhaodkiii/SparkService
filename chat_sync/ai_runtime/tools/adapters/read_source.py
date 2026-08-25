from __future__ import annotations

from chat_sync.ai_runtime.protocols.tool_protocol import BaseTool, ToolDefinition, ToolResult

from ._common import context_or_error


class ReadSourceTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_source",
            description="读取当前轮 Context Snapshot 中已授权的来源投影。",
            raw_parameters={
                "type": "object",
                "properties": {"source_id": {"type": "string", "maxLength": 160}},
                "required": ["source_id"],
                "additionalProperties": False,
            },
        )

    async def execute(self, *, source_id, _execution_context=None, **kwargs) -> ToolResult:
        context, error = context_or_error(_execution_context)
        if error:
            return error
        if context.context_snapshot_id is None:
            return ToolResult(content="当前轮没有可读取来源。", success=False, metadata={"error_code": "tool_source_missing"})
        from chat_sync.ai_models import ChatTurnContextSnapshot

        snapshot = ChatTurnContextSnapshot.objects.filter(pk=context.context_snapshot_id, run_id=context.run_id).first()
        if snapshot is None:
            return ToolResult(content="当前轮来源不可用。", success=False, metadata={"error_code": "tool_source_missing"})
        source = next((item for item in snapshot.sources if item.get("source_id") == source_id), None)
        if source is None:
            return ToolResult(content="来源不可用或无权访问。", success=False, metadata={"error_code": "tool_permission_denied"})
        if source.get("metadata", {}).get("content_status") == "unavailable":
            return ToolResult(content="该来源正文尚未完成安全抽取。", success=False, metadata={"error_code": "chat_attachment_content_unavailable"})
        return ToolResult(content="来源已在当前上下文中提供；可直接使用其引用信息。", sources=[{"source_id": source_id, "type": source.get("type", "source")}])
