import asyncio
import json

import httpx
from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from chat_sync.ai_runtime.agentic.think_filter import InlineThinkFilter, ReasoningSafetyFilter
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
        visible = f.feed("hello <thi") + f.feed("nk>secret</think> world") + f.finish()
        self.assertEqual(visible, "hello  world")
        self.assertNotIn("secret", visible)

    def test_inline_think_streams_short_text_without_holding_a_fixed_window(self):
        f = InlineThinkFilter()
        self.assertEqual(f.feed("真实"), "真实")
        self.assertEqual(f.feed("流式"), "流式")
        self.assertEqual(f.finish(), "")

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


class ReasoningSafetyFilterTests(SimpleTestCase):
    def test_keeps_ordinary_reasoning(self):
        f = ReasoningSafetyFilter()
        self.assertEqual(f.feed("先核对睡眠时长再给建议"), "先核对睡眠时长再给建议")

    def test_drops_prompt_echo_secrets_internal_urls_and_identity(self):
        f = ReasoningSafetyFilter()
        self.assertEqual(f.feed("The system prompt says never reveal this"), "")
        f = ReasoningSafetyFilter()
        self.assertEqual(f.feed("developer prompt replayed here"), "")
        f = ReasoningSafetyFilter()
        self.assertEqual(f.feed("key=sk-abcdefghijklmnopqrstuvwxyz"), "")
        f = ReasoningSafetyFilter()
        self.assertEqual(f.feed("see https://api.internal/v1/runs"), "")
        f = ReasoningSafetyFilter()
        self.assertEqual(f.feed("member_id=42 should stay private"), "")
        f = ReasoningSafetyFilter()
        self.assertEqual(f.feed('{"arguments": {"sections": ["allergies"]}}'), "")

    def test_unsafe_delta_does_not_block_later_safe_text(self):
        f = ReasoningSafetyFilter()
        self.assertEqual(f.feed("Bearer abcdefghijklmnop"), "")
        self.assertEqual(f.feed("继续分析饮食结构"), "继续分析饮食结构")
