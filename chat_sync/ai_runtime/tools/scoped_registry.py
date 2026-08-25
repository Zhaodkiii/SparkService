from __future__ import annotations

from typing import Any, Iterable

from chat_sync.ai_runtime.protocols.tool_protocol import ToolResult

from .policy import ToolExecutionContext
from .registry import RegisteredTool, ToolRegistry


class ScopedToolRegistry:
    def __init__(self, base: ToolRegistry, allowed_names: Iterable[str]) -> None:
        self.base = base
        self.allowed_names = frozenset(str(name) for name in allowed_names)

    def get(self, name: str) -> RegisteredTool | None:
        if name not in self.allowed_names:
            return None
        return self.base.get(name)

    def entries(self) -> list[RegisteredTool]:
        return [entry for entry in self.base.get_enabled(self.allowed_names)]

    def schemas(self) -> list[dict[str, Any]]:
        return [entry.schema for entry in self.entries()]

    async def execute(self, name: str, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        entry = self.get(name)
        if entry is None:
            return ToolResult(content="工具不可用或未授权。", success=False, metadata={"error_code": "tool_not_available"})
        return await entry.tool.execute(_execution_context=context, **arguments)


__all__ = ["ScopedToolRegistry"]
