from __future__ import annotations

from typing import Awaitable, Callable

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from chat_sync.ai_runtime.agentic.think_filter import InlineThinkFilter, ReasoningSafetyFilter
from chat_sync.ai_runtime.providers.types import ProviderChatRequest, ProviderGateway, ProviderChunk

logger = logging.getLogger("chat_sync.ai.round_runner")

# Classification thresholds for the DeferredFinalAnswerBuffer.
# A round's leading text is buffered, unclassified, until either threshold trips;
# whichever comes first promotes the buffer to a real-time final answer stream.
DEFAULT_STREAM_CLASSIFY_CHARS = 40
DEFAULT_STREAM_CLASSIFY_WINDOW_MS = 150


@dataclass
class AgenticRoundResult:
    text: str = ""
    reasoning: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    provider_request_id: str = ""


async def run_agentic_round(
    gateway: ProviderGateway,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]],
    on_chunk: Callable[[ProviderChunk], Awaitable[None]] | None = None,
    on_narration_delta: Callable[[str], Awaitable[None]] | None = None,
    on_final_chunk: Callable[[str], Awaitable[None]] | None = None,
    on_reasoning_delta: Callable[[str], Awaitable[None]] | None = None,
    stream_classify_chars: int = DEFAULT_STREAM_CLASSIFY_CHARS,
    stream_classify_window_ms: int = DEFAULT_STREAM_CLASSIFY_WINDOW_MS,
) -> AgenticRoundResult:
    """Run one Agentic Provider round.

    Text arrives before we know whether this round will call a tool, so leading
    text is buffered, unclassified, in a DeferredFinalAnswerBuffer:

    - If a ``tool_call_delta`` arrives first, the buffer is classified as
      narration and flushed through ``on_narration_delta``.
    - If a classify threshold trips first, the buffer is classified as the
      final answer and flushed through ``on_final_chunk``; every subsequent
      ``text_delta`` streams straight through in real time.

    Once classified as final, already-published text is never rolled back.
    Reasoning deltas are filtered and emitted independently of that classifier.
    ``round_id`` is the stable decimal string of the loop index for this Run.
    """
    result = AgenticRoundResult()
    calls: dict[int, dict[str, Any]] = {}
    narration_buffer: list[str] = []
    narration_confirmed = False
    final_stream_started = False
    round_started_at = time.monotonic()
    think_filter = InlineThinkFilter()
    reasoning_filter = ReasoningSafetyFilter()

    async def _emit_narration(text: str) -> None:
        if text and on_narration_delta is not None:
            await on_narration_delta(text)

    async def _emit_final(text: str) -> None:
        if text and on_final_chunk is not None:
            await on_final_chunk(text)

    def _classify_window_elapsed() -> bool:
        return (time.monotonic() - round_started_at) * 1000 >= stream_classify_window_ms

    async def _ingest_text(text_delta: str) -> None:
        nonlocal narration_confirmed, final_stream_started
        if not text_delta:
            return
        result.text += text_delta
        if narration_confirmed:
            await _emit_narration(text_delta)
        elif final_stream_started:
            await _emit_final(text_delta)
        else:
            narration_buffer.append(text_delta)
            buffered_len = sum(len(part) for part in narration_buffer)
            if on_final_chunk is not None and (
                buffered_len >= stream_classify_chars or _classify_window_elapsed()
            ):
                final_stream_started = True
                prefix = "".join(narration_buffer)
                narration_buffer.clear()
                await _emit_final(prefix)

    async for chunk in gateway.stream(
        ProviderChatRequest(messages=messages, tools=tools, tool_choice="auto" if tools else None, parallel_tool_calls=True if tools else None)
    ):
        if on_chunk is not None:
            await on_chunk(chunk)
        has_tool_call_deltas = bool(chunk.tool_call_deltas)
        if has_tool_call_deltas and not narration_confirmed and not final_stream_started:
            narration_confirmed = True
            prefix = "".join(narration_buffer)
            narration_buffer.clear()
            await _emit_narration(prefix)
        await _ingest_text(think_filter.feed(chunk.text_delta or ""))
        reasoning_delta = reasoning_filter.feed(chunk.reasoning_delta or "")
        if reasoning_delta:
            result.reasoning += reasoning_delta
            if on_reasoning_delta is not None:
                await on_reasoning_delta(reasoning_delta)
        result.finish_reason = chunk.finish_reason or result.finish_reason
        result.provider_request_id = chunk.provider_request_id or result.provider_request_id
        if chunk.usage:
            result.usage.update(chunk.usage)
        if has_tool_call_deltas:
            if final_stream_started:
                logger.warning(
                    "agentic_round.late_tool_call_after_final_stream provider_request_id=%s",
                    chunk.provider_request_id or result.provider_request_id,
                )
            else:
                for delta in chunk.tool_call_deltas:
                    item = calls.setdefault(delta.index, {"id": delta.call_id or f"tool_call_{delta.index}", "name": "", "arguments": ""})
                    if delta.call_id:
                        item["id"] = delta.call_id
                    if delta.name:
                        item["name"] = delta.name
                    item["arguments"] += delta.arguments_delta or ""
    await _ingest_text(think_filter.finish())
    if not narration_confirmed and not final_stream_started and narration_buffer:
        prefix = "".join(narration_buffer)
        narration_buffer.clear()
        if on_final_chunk is not None:
            final_stream_started = True
            await _emit_final(prefix)
    for item in calls.values():
        try:
            item["arguments"] = json.loads(item["arguments"] or "{}")
        except (TypeError, ValueError):
            item["arguments"] = None
    result.tool_calls = list(calls.values())
    return result
