"""CHAT-WEB-028: real Agentic final-answer streaming.

Covers the DeferredFinalAnswerBuffer classification state machine in
``round_runner.run_agentic_round`` / ``loop.run_agentic_loop`` (pure, no DB),
and the end-to-end wiring in ``run_tasks._execute_provider`` (DB-backed).
Plain-text and tool-using turns share this single pipeline.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from chat_sync.ai_models import RunStatus
from chat_sync.ai_runtime.agentic.loop import run_agentic_loop
from chat_sync.ai_runtime.agentic.round_runner import run_agentic_round
from chat_sync.ai_runtime.providers.types import ProviderChunk, ProviderRoute, ProviderToolCallDelta
from chat_sync.ai_services.stream_writer import StreamWriter
from chat_sync.ai_tasks.run_tasks import run_chat
from chat_sync.models import ChatThread
from chat_sync.tests.run_factory import canonical_run_payload


class _TextOnlyGateway:
    def __init__(self, chunks: list[str]):
        self.chunks = chunks

    async def stream(self, request):
        for text in self.chunks:
            yield ProviderChunk(text_delta=text)
        yield ProviderChunk(finish_reason="stop")


class _NarrationGateway:
    async def stream(self, request):
        yield ProviderChunk(text_delta="我先")
        yield ProviderChunk(text_delta="查", tool_call_deltas=[ProviderToolCallDelta(index=0, call_id="c1", name="read", arguments_delta="{}")])
        yield ProviderChunk(finish_reason="tool_calls")


class _LateToolCallGateway:
    async def stream(self, request):
        yield ProviderChunk(text_delta="12345")
        yield ProviderChunk(tool_call_deltas=[ProviderToolCallDelta(index=0, call_id="late", name="read", arguments_delta="{}")])
        yield ProviderChunk(finish_reason="stop")


class RoundRunnerFinalStreamClassificationTests(SimpleTestCase):
    """Pure round_runner.run_agentic_round classification behavior."""

    def test_no_tool_call_promotes_buffer_to_final_stream(self):
        gateway = _TextOnlyGateway(["这是", "最终", "答案"])
        final_deltas: list[str] = []
        narration_deltas: list[str] = []

        async def run():
            async def on_final_chunk(text):
                final_deltas.append(text)

            async def on_narration_delta(text):
                narration_deltas.append(text)

            return await run_agentic_round(
                gateway,
                [{"role": "user", "content": "hi"}],
                tools=[{"schema": {}}],
                on_final_chunk=on_final_chunk,
                on_narration_delta=on_narration_delta,
                stream_classify_chars=1,
                stream_classify_window_ms=150,
            )

        result = asyncio.run(run())
        self.assertEqual(result.text, "这是最终答案")
        self.assertEqual("".join(final_deltas), "这是最终答案")
        self.assertEqual(narration_deltas, [])
        self.assertEqual(result.tool_calls, [])

    def test_tool_call_in_same_or_later_chunk_still_uses_narration_channel(self):
        gateway = _NarrationGateway()
        final_deltas: list[str] = []
        narration_deltas: list[str] = []

        async def run():
            async def on_final_chunk(text):
                final_deltas.append(text)

            async def on_narration_delta(text):
                narration_deltas.append(text)

            return await run_agentic_round(
                gateway,
                [{"role": "user", "content": "hi"}],
                tools=[{"schema": {}}],
                on_final_chunk=on_final_chunk,
                on_narration_delta=on_narration_delta,
                # Default thresholds (40 chars / 150ms) never trip before the
                # tool_call_delta arrives on the second chunk.
            )

        result = asyncio.run(run())
        self.assertEqual("".join(narration_deltas), "我先查")
        self.assertEqual(final_deltas, [])
        self.assertEqual(len(result.tool_calls), 1)

    def test_late_tool_call_after_final_stream_is_dropped_not_rolled_back(self):
        gateway = _LateToolCallGateway()
        final_deltas: list[str] = []
        narration_deltas: list[str] = []

        async def run():
            async def on_final_chunk(text):
                final_deltas.append(text)

            async def on_narration_delta(text):
                narration_deltas.append(text)

            return await run_agentic_round(
                gateway,
                [{"role": "user", "content": "hi"}],
                tools=[{"schema": {}}],
                on_final_chunk=on_final_chunk,
                on_narration_delta=on_narration_delta,
                stream_classify_chars=1,
                stream_classify_window_ms=150,
            )

        with self.assertLogs("chat_sync.ai.round_runner", level="WARNING") as captured:
            result = asyncio.run(run())

        self.assertEqual("".join(final_deltas), "12345")
        self.assertEqual(narration_deltas, [])
        # The already-public final text is never retracted; the late tool
        # call is dropped instead of being executed or rolling back text.
        self.assertEqual(result.tool_calls, [])
        self.assertTrue(any("late_tool_call_after_final_stream" in message for message in captured.output))

    def test_on_final_chunk_none_preserves_legacy_full_buffer_behavior(self):
        gateway = _TextOnlyGateway(["legacy", "behavior"])

        async def run():
            return await run_agentic_round(
                gateway,
                [{"role": "user", "content": "hi"}],
                tools=[{"schema": {}}],
                stream_classify_chars=1,
                stream_classify_window_ms=1,
            )

        result = asyncio.run(run())
        # on_final_chunk is None, so classification never promotes the round
        # to a live stream regardless of how low the thresholds are.
        self.assertEqual(result.text, "legacybehavior")


class LoopFinalStreamWiringTests(SimpleTestCase):
    def test_run_agentic_loop_streams_final_answer_and_still_fires_completion_signal(self):
        gateway = _TextOnlyGateway(["最终", "答案"])
        final_deltas: list[str] = []
        final_text_calls: list[str] = []

        async def run():
            async def on_final_chunk(text):
                final_deltas.append(text)

            async def on_final_text(text):
                final_text_calls.append(text)

            return await run_agentic_loop(
                gateway,
                [{"role": "user", "content": "问"}],
                registry=object(),
                tool_schemas=[{"schema": {"type": "object"}}],
                execution_context=object(),
                on_final_chunk=on_final_chunk,
                on_final_text=on_final_text,
                stream_classify_chars=1,
                max_rounds=2,
            )

        final_text = asyncio.run(run())
        self.assertEqual("".join(final_deltas), "最终答案")
        self.assertEqual(final_text_calls, ["最终答案"])
        self.assertEqual(final_text, "最终答案")

    def test_forced_final_round_after_budget_exhaustion_streams_from_first_delta(self):
        class _ExhaustThenTextGateway:
            def __init__(self):
                self.calls = 0

            async def stream(self, request):
                self.calls += 1
                if self.calls == 1:
                    yield ProviderChunk(text_delta="先看看", tool_call_deltas=[ProviderToolCallDelta(index=0, call_id="c1", name="noop", arguments_delta="{}")])
                    yield ProviderChunk(finish_reason="tool_calls")
                else:
                    yield ProviderChunk(text_delta="最终")
                    yield ProviderChunk(text_delta="答案")
                    yield ProviderChunk(finish_reason="stop")

        gateway = _ExhaustThenTextGateway()
        final_deltas: list[str] = []
        narration_deltas: list[str] = []

        async def noop_dispatch(tool_calls, *, registry, context, max_calls, max_concurrency, on_tool_started=None, on_progress=None, seen=None):
            return []

        async def run():
            async def on_final_chunk(text):
                final_deltas.append(text)

            async def on_narration_delta(round_index, text):
                narration_deltas.append(text)

            with patch("chat_sync.ai_runtime.agentic.loop.dispatch_tool_calls", new=noop_dispatch):
                return await run_agentic_loop(
                    gateway,
                    [{"role": "user", "content": "问"}],
                    registry=object(),
                    tool_schemas=[{"schema": {"type": "object"}}],
                    execution_context=object(),
                    on_final_chunk=on_final_chunk,
                    on_narration_delta=on_narration_delta,
                    max_rounds=1,
                )

        final_text = asyncio.run(run())
        self.assertEqual(gateway.calls, 2)
        self.assertEqual(narration_deltas, ["先看看"])
        # Forced round has no tools to be ambiguous about, so it streams from
        # the very first delta instead of waiting out a classification window.
        self.assertEqual("".join(final_deltas), "最终答案")
        self.assertEqual(final_text, "最终答案")


class _ProviderRouteFactory:
    @staticmethod
    def make(supports_tool_use: bool = True) -> ProviderRoute:
        return ProviderRoute("doubao", "fake-model", "https://provider.test/v1", "secret", supports_tool_use=supports_tool_use)


def _agentic_context():
    return SimpleNamespace(
        messages=[{"role": "user", "content": "question"}],
        tool_manifest=({"name": "query_member_profile", "schema": {"type": "object"}},),
        context_hash="test-hash",
    )


class _InterleavedFinalAnswerGateway:
    """Sleeps between deltas so the AsyncTextDeltaBuffer's flush timer can
    fire mid-stream, proving text is written while generation is still in
    flight rather than only after the round completes."""

    def __init__(self):
        self.finished_at: float | None = None

    async def stream(self, request):
        for word in ["真实", "流式", "回答"]:
            yield ProviderChunk(text_delta=word)
            await asyncio.sleep(0.08)
        self.finished_at = time.monotonic()
        yield ProviderChunk(
            finish_reason="stop",
            provider_request_id="agentic-final",
            usage={"prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 8},
        )


@override_settings(
    CHAT_AI_SERVER_RUNS_ENABLED=True,
    CHAT_AI_RUN_EXECUTOR="provider",
    CHAT_AI_AGENTIC_TOOLS_ENABLED=True,
    CHAT_AI_OUTBOX_IMMEDIATE_RELAY=False,
)
class AgenticTrueStreamIntegrationTests(TransactionTestCase):
    reset_sequences = True

    def _make_run(self, idempotency_key: str):
        user = get_user_model().objects.create_user(username=f"agentic-stream-{idempotency_key}")
        thread = ChatThread.objects.create(user=user, title="Agentic true stream")
        from chat_sync.ai_services.run_service import RunService

        run = RunService.create_run(
            user=user,
            thread_id=thread.id,
            payload=canonical_run_payload(thread.id, content="question", client={}),
            idempotency_key=idempotency_key,
        ).run
        return run

    @override_settings(
        CHAT_AI_AGENTIC_STREAM_CLASSIFY_CHARS=1,
        CHAT_AI_AGENTIC_STREAM_CLASSIFY_WINDOW_MS=1,
    )
    def test_final_answer_streams_before_provider_finishes(self):
        run = self._make_run("agentic-stream-on")
        gateway = _InterleavedFinalAnswerGateway()
        write_times: list[float] = []
        original_append_text = StreamWriter.append_text

        def _spy_append_text(**kwargs):
            write_times.append(time.monotonic())
            return original_append_text(**kwargs)

        with (
            patch("chat_sync.ai_tasks.run_tasks.resolve_chat_route", return_value=_ProviderRouteFactory.make()),
            patch("chat_sync.ai_tasks.run_tasks.create_chat_gateway", return_value=gateway),
            patch("chat_sync.ai_tasks.run_tasks.build_context_for_run", return_value=_agentic_context()),
            patch.object(StreamWriter, "append_text", side_effect=_spy_append_text),
        ):
            result = run_chat.run(str(run.id), expected_generation=1, request_id="test-request")

        run.refresh_from_db()
        self.assertEqual(result["status"], RunStatus.COMPLETED)
        self.assertEqual(run.assistant_message.blocks.get(kind="text").payload["text"]["_0"], "真实流式回答")
        self.assertTrue(write_times, "expected at least one append_text call")
        self.assertLess(min(write_times), gateway.finished_at, "first write must happen before the provider stream finished")

    @override_settings(
        CHAT_AI_AGENTIC_STREAM_CLASSIFY_CHARS=1,
        CHAT_AI_AGENTIC_STREAM_CLASSIFY_WINDOW_MS=1,
    )
    def test_cancel_during_streaming_leaves_no_new_deltas(self):
        run = self._make_run("agentic-stream-cancel")

        class _CancelDuringStreamGateway:
            async def stream(self, request):
                from asgiref.sync import sync_to_async

                from chat_sync.ai_services.run_service import RunService

                yield ProviderChunk(text_delta="部分内容")
                await sync_to_async(RunService.request_cancel, thread_sensitive=True)(user_id=run.user_id, run_id=run.id)
                yield ProviderChunk(text_delta="不应写入的内容")
                yield ProviderChunk(finish_reason="stop")

        with (
            patch("chat_sync.ai_tasks.run_tasks.resolve_chat_route", return_value=_ProviderRouteFactory.make()),
            patch("chat_sync.ai_tasks.run_tasks.create_chat_gateway", return_value=_CancelDuringStreamGateway()),
            patch("chat_sync.ai_tasks.run_tasks.build_context_for_run", return_value=_agentic_context()),
        ):
            result = run_chat.run(str(run.id), expected_generation=1, request_id="test-request")

        run.refresh_from_db()
        self.assertEqual(result["status"], RunStatus.CANCELLED)
        text = run.assistant_message.blocks.filter(kind="text").first()
        if text is not None:
            self.assertNotIn("不应写入的内容", text.payload.get("text", {}).get("_0", ""))
