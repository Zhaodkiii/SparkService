from __future__ import annotations

import asyncio
import json
from typing import Any

from chat_sync.ai_runtime.protocols.tool_protocol import ToolResult

from .policy import ToolExecutionContext, canonical_tool_args, validate_schema
from .scoped_registry import ScopedToolRegistry


def _error(code: str, message: str, *, retryable: bool = False) -> ToolResult:
    return ToolResult(
        content=message,
        success=False,
        metadata={"error_code": code, "retryable": retryable},
    )


async def execute_tool_call(
    registry: ScopedToolRegistry,
    *,
    name: str,
    arguments: Any,
    context: ToolExecutionContext,
    request_id: str = "",
) -> ToolResult:
    entry = registry.get(name)
    if entry is None:
        return _error("tool_not_available", "工具不可用或未授权。")
    if not isinstance(arguments, dict):
        return _error("invalid_arguments", "工具参数必须是 JSON 对象。")
    try:
        encoded = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return _error("invalid_arguments", "工具参数不是有效 JSON。")
    if len(encoded.encode("utf-8")) > 32_768:
        return _error("arguments_too_large", "工具参数超出大小限制。")
    schema_errors = validate_schema(entry.schema["function"].get("parameters", {}), arguments)
    if schema_errors:
        return _error("schema_validation_failed", f"工具参数校验失败：{'; '.join(schema_errors[:4])}")

    execution_context = ToolExecutionContext(
        run_id=context.run_id,
        thread_id=context.thread_id,
        user_id=context.user_id,
        member_id=context.member_id,
        context_snapshot_id=context.context_snapshot_id,
        context_hash=context.context_hash,
        lease_token=context.lease_token,
        request_id=request_id or context.request_id,
        deadline_at=context.deadline_at,
    )
    try:
        result = await asyncio.wait_for(
            registry.execute(name, arguments, execution_context),
            timeout=max(0.1, float(entry.policy.timeout_seconds)),
        )
    except asyncio.TimeoutError:
        return _error("tool_timeout", "工具执行超时。", retryable=True)
    except asyncio.CancelledError:
        raise
    except Exception:
        return _error("tool_execution_failed", "工具执行失败，请稍后重试。", retryable=True)
    if not isinstance(result, ToolResult):
        result = ToolResult(content=str(result), metadata={})
    result.metadata = {**result.metadata, "tool": name, "arguments_hash": canonical_tool_args(name, entry.policy.version, arguments)}
    return result


__all__ = ["execute_tool_call"]
