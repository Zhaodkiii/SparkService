from __future__ import annotations

from typing import Awaitable, Callable

import json
from dataclasses import dataclass, field
from typing import Any

from chat_sync.ai_runtime.providers.types import ProviderChatRequest, ProviderGateway, ProviderChunk


@dataclass
class AgenticRoundResult:
    text: str = ""
    reasoning: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


async def run_text_round(
    gateway: ProviderGateway,
    messages: list[dict[str, str]],
    on_chunk: Callable[[ProviderChunk], Awaitable[None]],
) -> None:
    async for chunk in gateway.stream(ProviderChatRequest(messages=messages)):
        await on_chunk(chunk)


async def run_agentic_round(
    gateway: ProviderGateway,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]],
    on_chunk: Callable[[ProviderChunk], Awaitable[None]] | None = None,
) -> AgenticRoundResult:
    result = AgenticRoundResult()
    calls: dict[int, dict[str, Any]] = {}
    async for chunk in gateway.stream(
        ProviderChatRequest(messages=messages, tools=tools, tool_choice="auto", parallel_tool_calls=True)
    ):
        if on_chunk is not None:
            await on_chunk(chunk)
        result.text += chunk.text_delta or ""
        result.reasoning += chunk.reasoning_delta or ""
        result.finish_reason = chunk.finish_reason or result.finish_reason
        if chunk.usage:
            result.usage.update(chunk.usage)
        for delta in chunk.tool_call_deltas:
            item = calls.setdefault(delta.index, {"id": delta.call_id or f"tool_call_{delta.index}", "name": "", "arguments": ""})
            if delta.call_id:
                item["id"] = delta.call_id
            if delta.name:
                item["name"] = delta.name
            item["arguments"] += delta.arguments_delta or ""
    for item in calls.values():
        try:
            item["arguments"] = json.loads(item["arguments"] or "{}")
        except (TypeError, ValueError):
            item["arguments"] = None
    result.tool_calls = list(calls.values())
    return result
