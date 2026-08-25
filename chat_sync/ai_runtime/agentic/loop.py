from __future__ import annotations

from typing import Any, Awaitable, Callable

from .round_runner import run_agentic_round, run_text_round
from chat_sync.ai_runtime.providers.types import ProviderGateway, ProviderChunk
from chat_sync.ai_runtime.tools.dispatcher import ToolDispatchItem, dispatch_tool_calls
from chat_sync.ai_runtime.tools.policy import ToolExecutionContext
from chat_sync.ai_runtime.tools.scoped_registry import ScopedToolRegistry
from chat_sync.ai_runtime.protocols.tool_protocol import AgentLoopOutcome, ToolPauseRequest
from .messages import assistant_message_with_tool_calls


async def run_text_loop(
    gateway: ProviderGateway,
    messages: list[dict[str, str]],
    on_chunk: Callable[[ProviderChunk], Awaitable[None]],
) -> None:
    # P2 deliberately has one bounded text round; Agentic tool loops start in P4.
    await run_text_round(gateway, messages, on_chunk)


async def run_agentic_loop(
    gateway: ProviderGateway,
    messages: list[dict[str, Any]],
    *,
    registry: ScopedToolRegistry,
    tool_schemas: list[dict[str, Any]],
    execution_context: ToolExecutionContext,
    on_chunk: Callable[[ProviderChunk], Awaitable[None]] | None = None,
    on_tool_calls: Callable[[int, list[dict[str, Any]]], Awaitable[None]] | None = None,
    on_tool_results: Callable[[int, list[ToolDispatchItem]], Awaitable[None]] | None = None,
    on_pause: Callable[[int, ToolDispatchItem, list[dict[str, Any]]], Awaitable[None]] | None = None,
    on_final_text: Callable[[str], Awaitable[None]] | None = None,
    max_rounds: int = 8,
    max_calls_per_round: int = 8,
    max_concurrency: int = 4,
) -> str | AgentLoopOutcome:
    """Bounded Think/Act/Observe loop. Mutates ``messages`` into the model transcript."""
    final_text = ""
    for round_index in range(max(1, max_rounds)):
        result = await run_agentic_round(gateway, messages, tools=tool_schemas, on_chunk=on_chunk)
        if not result.tool_calls:
            final_text = result.text.strip()
            if final_text and on_final_text is not None:
                await on_final_text(final_text)
            return final_text
        messages.append(assistant_message_with_tool_calls(result.text, result.tool_calls))
        if on_tool_calls is not None:
            await on_tool_calls(round_index, result.tool_calls)
        dispatched = await dispatch_tool_calls(
            result.tool_calls,
            registry=registry,
            context=execution_context,
            max_calls=max_calls_per_round,
            max_concurrency=max_concurrency,
        )
        pause_item: ToolDispatchItem | None = None
        completed_items: list[ToolDispatchItem] = []
        for item in dispatched:
            if item.result.pause_for_user is not None:
                if pause_item is None:
                    pause_item = item
                continue
            messages.append({
                "role": "tool",
                "tool_call_id": item.call_id,
                "name": item.name,
                "content": item.result.content,
            })
            completed_items.append(item)
        if on_tool_results is not None:
            await on_tool_results(round_index, completed_items)
        if pause_item is not None:
            raw_pause = pause_item.result.pause_for_user or {}
            pause = ToolPauseRequest(
                kind=str(raw_pause.get("kind") or "ask_user"),
                request_schema=dict(raw_pause.get("request_schema") or raw_pause.get("schema") or {}),
                expires_in_seconds=int(raw_pause.get("expires_in_seconds") or 600),
                required_platform=str(raw_pause.get("required_platform") or ""),
                required_capability=str(raw_pause.get("required_capability") or ""),
                tool_version=str(raw_pause.get("tool_version") or "v1"),
                fallback_behavior=str(raw_pause.get("fallback_behavior") or "return_unavailable"),
            )
            if on_pause is not None:
                await on_pause(round_index, pause_item, messages)
            return AgentLoopOutcome(kind="paused", pause=pause, pause_tool_call_id=pause_item.call_id)
    # Force a final answer without tools after the loop budget is exhausted.
    forced = await run_agentic_round(gateway, messages, tools=[], on_chunk=on_chunk)
    final_text = forced.text.strip()
    if final_text and on_final_text is not None:
        await on_final_text(final_text)
    return final_text
