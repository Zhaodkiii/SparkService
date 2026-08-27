from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .round_runner import (
    DEFAULT_STREAM_CLASSIFY_CHARS,
    DEFAULT_STREAM_CLASSIFY_WINDOW_MS,
    AgenticRoundResult,
    run_agentic_round,
)
from chat_sync.ai_runtime.providers.types import ProviderGateway, ProviderChunk
from chat_sync.ai_runtime.tools.dispatcher import ToolDispatchItem, dispatch_tool_calls
from chat_sync.ai_runtime.tools.policy import ToolExecutionContext
from chat_sync.ai_runtime.tools.scoped_registry import ScopedToolRegistry
from chat_sync.ai_runtime.protocols.tool_protocol import AgentLoopOutcome, ToolPauseRequest
from .messages import assistant_message_with_tool_calls


@dataclass
class RoundTraceEvent:
    """Round-granular trace projection (narration vs final answer, usage).

    ``index`` is the stable round identifier for this Run; callers stringify it
    as ``round_id`` (it is not reassigned or reordered during the Run).
    """

    event: str  # started / completed / failed
    index: int
    call_id: str = ""
    call_role: str = ""  # narration / finish
    content: str = ""
    finish_reason: str = ""
    error_code: str = ""
    retryable: bool = False
    usage: dict[str, Any] = field(default_factory=dict)


async def run_agentic_loop(
    gateway: ProviderGateway,
    messages: list[dict[str, Any]],
    *,
    registry: ScopedToolRegistry,
    tool_schemas: list[dict[str, Any]],
    execution_context: ToolExecutionContext,
    on_chunk: Callable[[ProviderChunk], Awaitable[None]] | None = None,
    on_tool_calls: Callable[[int, list[dict[str, Any]]], Awaitable[None]] | None = None,
    on_tool_started: Callable[[str], Awaitable[None]] | None = None,
    on_progress: Callable[[str, str, float | None], Awaitable[None]] | None = None,
    on_narration_delta: Callable[[int, str], Awaitable[None]] | None = None,
    on_reasoning_delta: Callable[[int, str], Awaitable[None]] | None = None,
    on_tool_results: Callable[[int, list[ToolDispatchItem]], Awaitable[None]] | None = None,
    on_pause: Callable[[int, ToolDispatchItem, list[dict[str, Any]]], Awaitable[None]] | None = None,
    on_final_text: Callable[[str], Awaitable[None]] | None = None,
    on_final_chunk: Callable[[str], Awaitable[None]] | None = None,
    on_round: Callable[[RoundTraceEvent], Awaitable[None]] | None = None,
    max_rounds: int = 8,
    max_calls_per_round: int = 8,
    max_concurrency: int = 4,
    stream_classify_chars: int = DEFAULT_STREAM_CLASSIFY_CHARS,
    stream_classify_window_ms: int = DEFAULT_STREAM_CLASSIFY_WINDOW_MS,
) -> str | AgentLoopOutcome:
    """Bounded Think/Act/Observe loop. Mutates ``messages`` into the model transcript.

    ``tools=[]`` is a plain-text conversation: one Provider round, no tool
    dispatch, same stream classification and reasoning callbacks.
    """
    final_text = ""
    seen_calls: dict[str, str] = {}
    offered_tools = list(tool_schemas)
    for round_index in range(max(1, max_rounds)):
        if on_round is not None:
            await on_round(RoundTraceEvent(event="started", index=round_index))
        result: AgenticRoundResult
        try:
            async def _narration(delta: str, *, _round=round_index) -> None:
                if on_narration_delta is not None:
                    await on_narration_delta(_round, delta)

            async def _reasoning(delta: str, *, _round=round_index) -> None:
                if on_reasoning_delta is not None:
                    await on_reasoning_delta(_round, delta)

            result = await run_agentic_round(
                gateway,
                messages,
                tools=offered_tools,
                on_chunk=on_chunk,
                on_narration_delta=_narration,
                on_final_chunk=on_final_chunk,
                on_reasoning_delta=_reasoning,
                stream_classify_chars=stream_classify_chars if offered_tools else 0,
                stream_classify_window_ms=stream_classify_window_ms if offered_tools else 0,
            )
        except Exception:
            if on_round is not None:
                await on_round(RoundTraceEvent(event="failed", index=round_index, error_code="round_error", retryable=True))
            raise
        if on_round is not None:
            await on_round(RoundTraceEvent(
                event="completed",
                index=round_index,
                call_id=result.provider_request_id,
                call_role="narration" if result.tool_calls else "finish",
                content=result.text,
                finish_reason=result.finish_reason,
                usage=result.usage,
            ))
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
            on_tool_started=on_tool_started,
            on_progress=on_progress,
            seen=seen_calls,
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
    if on_round is not None:
        await on_round(RoundTraceEvent(event="started", index=max_rounds))

    async def _forced_reasoning(delta: str) -> None:
        if on_reasoning_delta is not None:
            await on_reasoning_delta(max_rounds, delta)

    forced = await run_agentic_round(
        gateway,
        messages,
        tools=[],
        on_chunk=on_chunk,
        on_final_chunk=on_final_chunk,
        on_reasoning_delta=_forced_reasoning,
        stream_classify_chars=0,
        stream_classify_window_ms=0,
    )
    if on_round is not None:
        await on_round(RoundTraceEvent(
            event="completed",
            index=max_rounds,
            call_id=forced.provider_request_id,
            call_role="finish",
            content=forced.text,
            finish_reason=forced.finish_reason,
            usage=forced.usage,
        ))
    final_text = forced.text.strip()
    if final_text and on_final_text is not None:
        await on_final_text(final_text)
    return final_text
