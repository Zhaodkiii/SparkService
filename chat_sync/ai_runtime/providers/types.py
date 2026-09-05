from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol


@dataclass(frozen=True)
class ProviderRoute:
    provider: str
    model: str
    endpoint: str
    api_key: str
    config_version: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    supports_tool_use: bool = False
    supports_parallel_tool_calls: bool = False
    supports_multimodal: bool = False
    context_window: int | None = None


@dataclass(frozen=True)
class ProviderChatRequest:
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] = field(default_factory=list)
    tool_choice: str | dict[str, Any] | None = "auto"
    parallel_tool_calls: bool | None = None
    request_id: str = ""


@dataclass(frozen=True)
class ProviderToolCallDelta:
    index: int
    call_id: str = ""
    name: str = ""
    arguments_delta: str = ""


@dataclass
class ProviderChunk:
    text_delta: str = ""
    reasoning_delta: str = ""
    finish_reason: str = ""
    provider_request_id: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    tool_call_deltas: list[ProviderToolCallDelta] = field(default_factory=list)


class ProviderGateway(Protocol):
    async def stream(self, request: ProviderChatRequest) -> AsyncIterator[ProviderChunk]: ...
