from __future__ import annotations

from typing import Any

from chat_sync.ai_runtime.protocols.tool_protocol import ToolResult
from chat_sync.ai_runtime.tools.policy import ToolExecutionContext


def context_or_error(value: Any) -> tuple[ToolExecutionContext | None, ToolResult | None]:
    if not isinstance(value, ToolExecutionContext):
        return None, ToolResult(content="工具执行上下文不可用。", success=False, metadata={"error_code": "tool_context_missing"})
    if value.member_id is None:
        return None, ToolResult(content="当前会话没有可用成员。", success=False, metadata={"error_code": "tool_member_missing"})
    return value, None


def safe_text(value: Any, limit: int = 1200) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]
