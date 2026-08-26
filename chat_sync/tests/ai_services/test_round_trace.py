from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from chat_sync.ai_models import ChatUsageRecord, RunStatus
from chat_sync.ai_services.run_service import RunService
from chat_sync.ai_services.stream_writer import StreamWriter
from chat_sync.ai_runtime.agentic.loop import run_agentic_loop
from chat_sync.ai_runtime.agentic.round_runner import run_agentic_round
from chat_sync.ai_runtime.providers.types import ProviderChunk, ProviderToolCallDelta
from chat_sync.models import ChatThread
from chat_sync.tests.run_factory import canonical_run_payload


def _make_run():
    user = get_user_model().objects.create_user(username=f"round-{uuid.uuid4().hex[:8]}")
    thread = ChatThread.objects.create(user=user, title="Round")
    run = RunService.create_run(
        user=user,
        thread_id=thread.id,
        payload=canonical_run_payload(thread.id, content="请回答", client={"platform": "web", "version": "p4", "device_id": "test"}),
        idempotency_key=f"round-{uuid.uuid4().hex[:8]}",
    ).run
    return RunService.claim_for_execution(run_id=run.id, expected_generation=1)


@override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled", CHAT_AI_OUTBOX_IMMEDIATE_RELAY=False)
class RoundTraceWriterTests(TestCase):
    def test_round_events_and_usage_aggregation_are_replayable(self):
        run = _make_run()
        lease = run.lease_token
        StreamWriter.round_started(run_id=run.id, round_id="0", index=0, call_id=None, lease_token=lease)
        StreamWriter.round_completed(
            run_id=run.id, round_id="0", index=0, call_id="req-0", call_role="narration",
            content="我先查一下", finish_reason="tool_calls", lease_token=lease,
        )
        StreamWriter.usage_updated(run_id=run.id, usage={"prompt_tokens": 10, "completion_tokens": 3}, lease_token=lease)
        StreamWriter.round_started(run_id=run.id, round_id="1", index=1, call_id=None, lease_token=lease)
        StreamWriter.round_completed(
            run_id=run.id, round_id="1", index=1, call_id="req-1", call_role="finish",
            content="答案是 X", finish_reason="stop", lease_token=lease,
        )
        finished = StreamWriter.finish(
            run_id=run.id, status=RunStatus.COMPLETED, lease_token=lease,
            usage={"prompt_tokens": 10, "completion_tokens": 3}, model_calls=2, tool_calls=1,
        )

        rounds = list(finished.events.filter(type__startswith="agent.round.").values_list("type", "payload"))
        self.assertEqual([t for t, _ in rounds], ["agent.round.started", "agent.round.completed", "agent.round.started", "agent.round.completed"])
        self.assertEqual(rounds[1][1]["call_role"], "narration")
        self.assertEqual(rounds[1][1]["content"], "我先查一下")
        self.assertEqual(rounds[3][1]["call_role"], "finish")
        self.assertEqual(rounds[3][1]["content"], "答案是 X")
        self.assertEqual(finished.events.filter(type="usage.updated").count(), 1)

        usage = ChatUsageRecord.objects.get(run=finished)
        self.assertEqual(usage.model_calls, 2)
        self.assertEqual(usage.tool_calls, 1)
        final_usage = finished.events.get(type="usage.final").payload
        self.assertEqual(final_usage["model_calls"], 2)
        self.assertEqual(final_usage["tool_calls"], 1)


class _RoundGateway:
    def __init__(self):
        self.calls = 0

    async def stream(self, request):
        self.calls += 1
        if self.calls == 1:
            yield ProviderChunk(text_delta="我先查", provider_request_id="req-0", tool_call_deltas=[ProviderToolCallDelta(index=0, call_id="call-1", name="read", arguments_delta="{}")])
            yield ProviderChunk(finish_reason="tool_calls", provider_request_id="req-0", usage={"prompt_tokens": 10, "completion_tokens": 3})
        else:
            yield ProviderChunk(text_delta="答案", provider_request_id="req-1")
            yield ProviderChunk(finish_reason="stop", provider_request_id="req-1", usage={"prompt_tokens": 5, "completion_tokens": 2})


class RoundLoopSemanticsTests(TestCase):
    def test_narration_stays_in_trace_and_final_answer_is_promoted(self):
        gateway = _RoundGateway()
        events = []

        async def on_round(trace):
            events.append(trace)

        async def emit():
            async def noop_dispatch(tool_calls, *, registry, context, max_calls, max_concurrency, on_tool_started=None, on_progress=None, seen=None):
                return []

            with patch("chat_sync.ai_runtime.agentic.loop.dispatch_tool_calls", new=noop_dispatch):
                return await run_agentic_loop(
                    gateway,
                    [{"role": "user", "content": "问"}],
                    registry=object(),
                    tool_schemas=[{"schema": {"type": "object"}}],
                    execution_context=object(),
                    on_round=on_round,
                    max_rounds=4,
                )

        final_text = async_to_sync(emit)()

        kinds = [e.event for e in events]
        self.assertEqual(kinds, ["started", "completed", "started", "completed"])
        self.assertEqual(events[1].call_role, "narration")
        self.assertEqual(events[1].content, "我先查")
        self.assertEqual(events[1].call_id, "req-0")
        self.assertEqual(events[3].call_role, "finish")
        self.assertEqual(events[3].content, "答案")
        self.assertEqual(final_text.strip(), "答案")


class _NarrationGateway:
    async def stream(self, request):
        yield ProviderChunk(text_delta="我先")
        yield ProviderChunk(text_delta="查", tool_call_deltas=[ProviderToolCallDelta(index=0, call_id="c1", name="read", arguments_delta="{}")])
        yield ProviderChunk(finish_reason="tool_calls")


class _TextOnlyGateway:
    def __init__(self, text: str):
        self.text = text

    async def stream(self, request):
        yield ProviderChunk(text_delta=self.text)
        yield ProviderChunk(finish_reason="stop")


class RoundRunnerNarrationTests(SimpleTestCase):
    def test_narration_streams_only_after_tool_confirmation(self):
        gateway = _NarrationGateway()
        deltas: list[str] = []

        async def run():
            async def on_narration_delta(text):
                deltas.append(text)

            return await run_agentic_round(gateway, [{"role": "user", "content": "hi"}], tools=[{"schema": {}}], on_narration_delta=on_narration_delta)

        result = asyncio.run(run())
        self.assertEqual(result.text, "我先查")
        self.assertEqual("".join(deltas), "我先查")

    def test_final_answer_round_does_not_emit_narration_deltas(self):
        gateway = _TextOnlyGateway("这是最终答案")
        deltas: list[str] = []

        async def run():
            async def on_narration_delta(text):
                deltas.append(text)

            return await run_agentic_round(gateway, [{"role": "user", "content": "hi"}], tools=[{"schema": {}}], on_narration_delta=on_narration_delta)

        result = asyncio.run(run())
        self.assertEqual(result.text, "这是最终答案")
        self.assertEqual(deltas, [])