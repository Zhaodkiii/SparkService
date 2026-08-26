from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from chat_sync.ai_runtime.protocols.tool_protocol import ToolResult

from .executor import execute_tool_call
from .policy import ToolExecutionContext, canonical_tool_args
from .scoped_registry import ScopedToolRegistry


@dataclass(frozen=True)
class ToolDispatchItem:
    call_id: str
    name: str
    arguments: dict[str, Any]
    result: ToolResult
    duplicate_of: str = ""


async def dispatch_tool_calls(
    calls: list[dict[str, Any]],
    *,
    registry: ScopedToolRegistry,
    context: ToolExecutionContext,
    max_calls: int = 8,
    max_concurrency: int = 4,
    on_tool_started: Callable[[str], Awaitable[None]] | None = None,
    on_progress: Callable[[str, str, float | None], Awaitable[None]] | None = None,
    seen: dict[str, str] | None = None,
) -> list[ToolDispatchItem]:
    """Validate and execute one model tool-call batch, preserving provider order.

    ``seen`` maps a canonical-arguments key to the first ``call_id`` that produced
    a *successful* result earlier in the Run. Populating it across rounds makes
    identical (including empty-argument) tool calls deduplicate cross-round instead
    of re-executing; failures are deliberately excluded so a retry still runs.
    """
    ordered = calls[:16]
    results: list[ToolDispatchItem | None] = [None] * len(ordered)
    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    batch_seen: dict[str, str] = {}
    run_seen = seen if seen is not None else {}
    executable = 0

    async def one(index: int, call: dict[str, Any]) -> None:
        nonlocal executable
        call_id = str(call.get("id") or f"tool_call_{index}")[:128]
        name = str(call.get("name") or "")[:128]
        arguments = call.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except (TypeError, ValueError):
                arguments = None
        if not isinstance(arguments, dict):
            results[index] = ToolDispatchItem(call_id, name, {}, ToolResult(content="工具参数不是有效 JSON。", success=False, metadata={"error_code": "invalid_arguments"}))
            return
        entry = registry.get(name)
        if entry is None:
            results[index] = ToolDispatchItem(call_id, name, arguments, ToolResult(content="工具不可用或未授权。", success=False, metadata={"error_code": "tool_not_available"}))
            return
        key = canonical_tool_args(name, entry.policy.version, arguments)
        prior_call_id = run_seen.get(key)
        if prior_call_id:
            results[index] = ToolDispatchItem(call_id, name, arguments, ToolResult(content="本轮已复用先前相同工具调用结果。", success=False, metadata={"error_code": "duplicate_tool_call", "duplicate_of": prior_call_id}), duplicate_of=prior_call_id)
            return
        if key in batch_seen:
            results[index] = ToolDispatchItem(call_id, name, arguments, ToolResult(content="本轮已执行相同工具调用，复用已有结果。", success=False, metadata={"error_code": "duplicate_tool_call", "duplicate_of": batch_seen[key]}), duplicate_of=batch_seen[key])
            return
        batch_seen[key] = call_id
        if executable >= max_calls:
            results[index] = ToolDispatchItem(call_id, name, arguments, ToolResult(content="本轮工具调用数量已达上限。", success=False, metadata={"error_code": "tool_call_limit"}))
            return
        executable += 1
        async with semaphore:
            if on_tool_started is not None:
                await on_tool_started(call_id)

            async def _progress(message: str, percent: float | None) -> None:
                if on_progress is not None:
                    await on_progress(call_id, message, percent)

            result = await execute_tool_call(
                registry, name=name, arguments=arguments, context=context, request_id=call_id, on_progress=_progress,
            )
        results[index] = ToolDispatchItem(call_id, name, arguments, result)
        if result.success:
            run_seen[key] = call_id

    await asyncio.gather(*(one(i, call) for i, call in enumerate(ordered)))
    return [item for item in results if item is not None]


__all__ = ["ToolDispatchItem", "dispatch_tool_calls"]
