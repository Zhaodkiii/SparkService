import asyncio
import json

import httpx
from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from chat_sync.ai_runtime.agentic.think_filter import InlineThinkFilter
from chat_sync.ai_runtime.providers.openai_compatible import OpenAICompatibleGateway
from chat_sync.ai_runtime.providers.exceptions import LLMTimeoutError
from chat_sync.ai_runtime.providers.types import ProviderChatRequest, ProviderRoute


class _DelayedStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        await asyncio.sleep(0.05)
        yield b'data: {"choices":[{"delta":{"content":"late"}}]}\n\n'

    async def aclose(self):
        return None


class P2TextRuntimeTests(SimpleTestCase):
    def test_inline_think_is_not_visible(self):
        f = InlineThinkFilter()
        self.assertEqual(f.feed("hello <thi"), "he")
        self.assertEqual(f.feed("nk>secret</think> world"), "llo ")
        self.assertEqual(f.finish(), " world")

    def test_openai_endpoint_normalization(self):
        gateway = OpenAICompatibleGateway(ProviderRoute("doubao", "model", "https://example.test/v1", "secret"))
        self.assertEqual(gateway.endpoint, "https://example.test/v1/chat/completions")

    def test_openai_compatible_sse_maps_text_reasoning_and_usage(self):
        captured = {}

        def handler(request: httpx.Request):
            captured["url"] = str(request.url)
            captured["authorization"] = request.headers["Authorization"]
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                text=(
                    'data: {"id":"req-1","choices":[{"delta":{"reasoning_content":"private","content":"hello"},"finish_reason":null}]}\n\n'
                    'data: {"id":"req-1","choices":[{"delta":{"content":" world"},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5,"completion_tokens_details":{"reasoning_tokens":1}}}\n\n'
                    "data: [DONE]\n\n"
                ),
            )

        gateway = OpenAICompatibleGateway(
            ProviderRoute("doubao", "model", "https://example.test/v1", "server-secret"),
            transport=httpx.MockTransport(handler),
        )

        async def collect():
            return [chunk async for chunk in gateway.stream(ProviderChatRequest(messages=[{"role": "user", "content": "hi"}]))]

        chunks = async_to_sync(collect)()
        self.assertEqual("".join(chunk.text_delta for chunk in chunks), "hello world")
        self.assertEqual(chunks[0].reasoning_delta, "private")
        self.assertEqual(chunks[-1].usage["reasoning_tokens"], 1)
        self.assertEqual(chunks[-1].finish_reason, "stop")
        self.assertEqual(captured["authorization"], "Bearer server-secret")
        self.assertNotIn("server-secret", json.dumps(captured["body"]))

    def test_first_event_timeout_is_distinct_from_idle_timeout(self):
        gateway = OpenAICompatibleGateway(
            ProviderRoute("doubao", "model", "https://example.test/v1", "secret"),
            first_event_timeout=0.01,
            idle_timeout=1,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=_DelayedStream())),
        )

        async def collect():
            return [chunk async for chunk in gateway.stream(ProviderChatRequest(messages=[]))]

        with self.assertRaises(LLMTimeoutError):
            async_to_sync(collect)()
