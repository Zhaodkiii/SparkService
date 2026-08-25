from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

import httpx

from .base import BaseProviderGateway
from .exceptions import LLMAPIError, LLMAuthenticationError, LLMParseError, LLMRateLimitError, LLMTimeoutError
from .types import ProviderChatRequest, ProviderChunk, ProviderRoute, ProviderToolCallDelta


class OpenAICompatibleGateway(BaseProviderGateway):
    def __init__(self, route: ProviderRoute, *, connect_timeout: float = 10, first_event_timeout: float = 30, idle_timeout: float = 30, max_output_chars: int = 100000, transport: httpx.AsyncBaseTransport | None = None):
        self.route = route
        self.connect_timeout = connect_timeout
        self.first_event_timeout = first_event_timeout
        self.idle_timeout = idle_timeout
        self.max_output_chars = max_output_chars
        self.transport = transport

    @property
    def endpoint(self) -> str:
        value = self.route.endpoint.rstrip("/")
        return value if value.endswith("/chat/completions") else f"{value}/chat/completions"

    async def stream(self, request: ProviderChatRequest) -> AsyncIterator[ProviderChunk]:
        timeout = httpx.Timeout(connect=self.connect_timeout, read=self.idle_timeout, write=self.idle_timeout, pool=self.connect_timeout)
        headers = {"Authorization": f"Bearer {self.route.api_key}", "Content-Type": "application/json"}
        body = {"model": self.route.model, "messages": request.messages, "stream": True}
        if request.tools:
            body["tools"] = request.tools
            if request.tool_choice is not None:
                body["tool_choice"] = request.tool_choice
            if request.parallel_tool_calls is not None:
                body["parallel_tool_calls"] = request.parallel_tool_calls
        if self.route.temperature is not None:
            body["temperature"] = self.route.temperature
        if self.route.max_tokens is not None:
            body["max_tokens"] = self.route.max_tokens
        visible = 0
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
                async with client.stream("POST", self.endpoint, headers=headers, json=body) as response:
                    if response.status_code == 401:
                        raise LLMAuthenticationError(provider=self.route.provider)
                    if response.status_code == 429:
                        raise LLMRateLimitError(provider=self.route.provider)
                    if response.status_code >= 400:
                        raise LLMAPIError("provider returned an error", status_code=response.status_code, provider=self.route.provider)
                    lines = response.aiter_lines().__aiter__()
                    first_data_deadline = time.monotonic() + self.first_event_timeout
                    first_data_received = False
                    while True:
                        try:
                            if first_data_received:
                                line = await lines.__anext__()
                            else:
                                remaining = first_data_deadline - time.monotonic()
                                line = await asyncio.wait_for(lines.__anext__(), timeout=max(0.001, remaining))
                        except StopAsyncIteration:
                            return
                        except asyncio.TimeoutError as exc:
                            raise LLMTimeoutError("provider first event timeout", provider=self.route.provider) from exc
                        if not line or not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            return
                        try:
                            item = json.loads(raw)
                        except json.JSONDecodeError as exc:
                            raise LLMParseError("invalid provider SSE payload", provider=self.route.provider) from exc
                        choice = (item.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        text = delta.get("content") or ""
                        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                        tool_call_deltas: list[ProviderToolCallDelta] = []
                        for raw_call in delta.get("tool_calls") or []:
                            if not isinstance(raw_call, dict):
                                continue
                            try:
                                index = int(raw_call.get("index", 0))
                            except (TypeError, ValueError):
                                raise LLMParseError("invalid provider tool call index", provider=self.route.provider)
                            function = raw_call.get("function") or {}
                            if not isinstance(function, dict):
                                function = {}
                            tool_call_deltas.append(
                                ProviderToolCallDelta(
                                    index=index,
                                    call_id=str(raw_call.get("id") or ""),
                                    name=str(function.get("name") or ""),
                                    arguments_delta=str(function.get("arguments") or ""),
                                )
                            )
                        visible += len(text)
                        if visible > self.max_output_chars:
                            raise LLMAPIError("provider output exceeded limit", status_code=413, provider=self.route.provider)
                        usage = item.get("usage") or {}
                        normalized_usage = {k: int(v) for k, v in usage.items() if isinstance(v, (int, float))}
                        completion_details = usage.get("completion_tokens_details") or {}
                        if isinstance(completion_details, dict) and isinstance(completion_details.get("reasoning_tokens"), (int, float)):
                            normalized_usage["reasoning_tokens"] = int(completion_details["reasoning_tokens"])
                        yield ProviderChunk(
                            text_delta=text,
                            reasoning_delta=reasoning,
                            finish_reason=choice.get("finish_reason") or "",
                            provider_request_id=str(item.get("id") or ""),
                            usage=normalized_usage,
                            tool_call_deltas=tool_call_deltas,
                        )
                        first_data_received = True
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(provider=self.route.provider) from exc
        except httpx.HTTPError as exc:
            raise LLMAPIError("provider connection failed", provider=self.route.provider) from exc
