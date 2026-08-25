"""Protocol adapter for deferred loading.

This adapter is intentionally not registered in the model-visible registry:
the API/service layer must authorize exact names before schemas enter a Run.
"""

from __future__ import annotations

from chat_sync.ai_runtime.protocols.tool_protocol import BaseTool, ToolDefinition, ToolResult
from chat_sync.ai_runtime.tools.deferred import validate_load_names


class LoadToolsTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="load_tools",
            description="请求装载已授权工具的精确 Schema；实际授权由服务端 API 完成。",
            raw_parameters={
                "type": "object",
                "properties": {"names": {"type": "array", "items": {"type": "string"}, "maxItems": 8}},
                "required": ["names"],
                "additionalProperties": False,
            },
        )

    async def execute(self, *, _execution_context=None, **arguments) -> ToolResult:
        try:
            names = validate_load_names(arguments.get("names") or [])
        except ValueError as exc:
            return ToolResult(content=str(exc), success=False, metadata={"error_code": "deferred_tool_names_invalid"})
        return ToolResult(
            content="工具装载请求已提交。",
            success=True,
            metadata={"deferred": True, "names": names, "requires_service_authorization": True},
        )


__all__ = ["LoadToolsTool"]
