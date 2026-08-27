"""CHAT-WEB-028: reasoning deltas persist as one deepThought Block and a public round channel."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from asgiref.sync import async_to_sync

from chat_sync.ai_models import RunStatus
from chat_sync.ai_runtime.agentic.round_runner import run_agentic_round
from chat_sync.ai_runtime.providers.types import ProviderChunk, ProviderRoute
from chat_sync.ai_services.run_service import RunService
from chat_sync.ai_services.stream_writer import StreamWriter
from chat_sync.ai_tasks.run_tasks import run_chat
from chat_sync.contracts import KIND_DEEP_THOUGHT
from chat_sync.models import ChatThread
from chat_sync.tests.run_factory import canonical_run_payload


class _ReasoningGateway:
    async def stream(self, request):
        yield ProviderChunk(reasoning_delta="先看")
        yield ProviderChunk(reasoning_delta="睡眠")
        yield ProviderChunk(text_delta="建议早点休息")
        yield ProviderChunk(
            finish_reason="stop",
            provider_request_id="reason-1",
            usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        )


class _UnsafeReasoningGateway:
    async def stream(self, request):
        yield ProviderChunk(reasoning_delta="The system prompt forbids leaking keys")
        yield ProviderChunk(reasoning_delta="sk-abcdefghijklmnopqrstuvwxyz")
        yield ProviderChunk(text_delta="这是安全的最终回答")
        yield ProviderChunk(finish_reason="stop", provider_request_id="reason-unsafe")


class RoundRunnerReasoningTests(SimpleTestCase):
    def test_reasoning_deltas_are_filtered_and_emitted_independently_of_final_text(self):
        emitted: list[str] = []
        final: list[str] = []

        async def run():
            async def on_reasoning_delta(text):
                emitted.append(text)

            async def on_final_chunk(text):
                final.append(text)

            return await run_agentic_round(
                _ReasoningGateway(),
                [{"role": "user", "content": "hi"}],
                tools=[],
                on_reasoning_delta=on_reasoning_delta,
                on_final_chunk=on_final_chunk,
                stream_classify_chars=0,
                stream_classify_window_ms=0,
            )

        result = async_to_sync(run)()
        self.assertEqual("".join(emitted), "先看睡眠")
        self.assertEqual("".join(final), "建议早点休息")
        self.assertEqual(result.reasoning, "先看睡眠")
        self.assertEqual(result.text, "建议早点休息")

    def test_unsafe_reasoning_is_dropped_without_blocking_the_answer(self):
        emitted: list[str] = []
        final: list[str] = []

        async def run():
            async def on_reasoning_delta(text):
                emitted.append(text)

            async def on_final_chunk(text):
                final.append(text)

            return await run_agentic_round(
                _UnsafeReasoningGateway(),
                [{"role": "user", "content": "hi"}],
                tools=[],
                on_reasoning_delta=on_reasoning_delta,
                on_final_chunk=on_final_chunk,
                stream_classify_chars=0,
                stream_classify_window_ms=0,
            )

        result = async_to_sync(run)()
        self.assertEqual(emitted, [])
        self.assertEqual("".join(final), "这是安全的最终回答")
        self.assertEqual(result.reasoning, "")
        self.assertEqual(result.text, "这是安全的最终回答")


def _provider_route() -> ProviderRoute:
    return ProviderRoute("doubao", "fake-model", "https://provider.test/v1", "secret")


def _text_context():
    return SimpleNamespace(messages=[{"role": "user", "content": "question"}], tool_manifest=[], context_hash="test-hash")


@override_settings(
    CHAT_AI_SERVER_RUNS_ENABLED=True,
    CHAT_AI_RUN_EXECUTOR="provider",
    CHAT_AI_OUTBOX_IMMEDIATE_RELAY=False,
)
class ReasoningPersistenceTests(TransactionTestCase):
    reset_sequences = True

    def _make_run(self, key: str):
        user = get_user_model().objects.create_user(username=f"reason-{key}")
        thread = ChatThread.objects.create(user=user, title="Reasoning")
        run = RunService.create_run(
            user=user,
            thread_id=thread.id,
            payload=canonical_run_payload(thread.id, content="question", client={}),
            idempotency_key=key,
        ).run
        return run

    def test_append_reasoning_creates_one_block_then_deltas_and_finish_freezes_duration(self):
        run = self._make_run("writer-only")
        run = RunService.claim_for_execution(run_id=run.id, expected_generation=1)
        StreamWriter.append_reasoning(run_id=run.id, text="先看", lease_token=run.lease_token)
        StreamWriter.append_reasoning(run_id=run.id, text="睡眠", lease_token=run.lease_token)
        StreamWriter.append_text(run_id=run.id, text="建议早点休息", lease_token=run.lease_token)
        finished = StreamWriter.finish(run_id=run.id, status=RunStatus.COMPLETED, lease_token=run.lease_token)

        thought = finished.assistant_message.blocks.get(kind=KIND_DEEP_THOUGHT)
        inner = thought.payload["deep_thought"]["_0"]
        self.assertEqual(inner["reasoning_content"], "先看睡眠")
        self.assertEqual(inner["reasoning_visibility"], "summary")
        self.assertFalse(inner["reasoning_expanded"])
        self.assertIsInstance(inner["reasoning_duration_ms"], int)
        self.assertGreaterEqual(inner["reasoning_duration_ms"], 0)
        self.assertEqual(thought.status, "ready")
        self.assertEqual(thought.order_key, 900)

        types = list(finished.events.filter(type__in=["block.created", "block.delta", "block.completed"]).values_list("type", "payload"))
        created_kinds = [payload.get("kind") or payload.get("block", {}).get("kind") for event_type, payload in types if event_type == "block.created"]
        self.assertEqual(created_kinds.count(KIND_DEEP_THOUGHT), 1)
        self.assertEqual(created_kinds.count("text"), 1)
        thought_deltas = [payload["delta"] for event_type, payload in types if event_type == "block.delta" and payload.get("block_id") == str(thought.id)]
        self.assertEqual(thought_deltas, ["先看", "睡眠"])
        self.assertEqual(sum(1 for event_type, payload in types if event_type == "block.completed" and payload.get("kind") == KIND_DEEP_THOUGHT), 1)

    def test_provider_run_emits_public_reasoning_channel_and_persists_deep_thought(self):
        run = self._make_run("provider-reason")
        with (
            patch("chat_sync.ai_tasks.run_tasks.resolve_chat_route", return_value=_provider_route()),
            patch("chat_sync.ai_tasks.run_tasks.create_chat_gateway", return_value=_ReasoningGateway()),
            patch("chat_sync.ai_tasks.run_tasks.build_context_for_run", return_value=_text_context()),
        ):
            result = run_chat.run(str(run.id), expected_generation=1, request_id="test-request")

        run.refresh_from_db()
        self.assertEqual(result["status"], RunStatus.COMPLETED)
        thought = run.assistant_message.blocks.get(kind=KIND_DEEP_THOUGHT)
        self.assertEqual(thought.payload["deep_thought"]["_0"]["reasoning_content"], "先看睡眠")
        self.assertFalse(thought.payload["deep_thought"]["_0"]["reasoning_expanded"])
        self.assertEqual(run.assistant_message.blocks.get(kind="text").payload["text"]["_0"], "建议早点休息")

        deltas = list(run.events.filter(type="agent.round.delta").order_by("sequence").values_list("payload", flat=True))
        reasoning = [item for item in deltas if item.get("channel") == "public_reasoning_summary"]
        self.assertTrue(reasoning)
        self.assertEqual("".join(item["text_delta"] for item in reasoning), "先看睡眠")
        self.assertEqual(run.events.filter(type="agent.round.started").count(), 1)
        self.assertEqual(run.events.filter(type="agent.round.completed").count(), 1)

    def test_unsafe_reasoning_never_creates_a_deep_thought_block(self):
        run = self._make_run("provider-unsafe")
        with (
            patch("chat_sync.ai_tasks.run_tasks.resolve_chat_route", return_value=_provider_route()),
            patch("chat_sync.ai_tasks.run_tasks.create_chat_gateway", return_value=_UnsafeReasoningGateway()),
            patch("chat_sync.ai_tasks.run_tasks.build_context_for_run", return_value=_text_context()),
        ):
            result = run_chat.run(str(run.id), expected_generation=1, request_id="test-request")

        run.refresh_from_db()
        self.assertEqual(result["status"], RunStatus.COMPLETED)
        self.assertFalse(run.assistant_message.blocks.filter(kind=KIND_DEEP_THOUGHT).exists())
        self.assertEqual(run.assistant_message.blocks.get(kind="text").payload["text"]["_0"], "这是安全的最终回答")
        self.assertFalse(run.events.filter(type="agent.round.delta", payload__channel="public_reasoning_summary").exists())
