from __future__ import annotations

from unittest.mock import patch
from types import SimpleNamespace

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from chat_sync.ai_models import ChatEventOutbox, ChatUsageRecord, RunStatus
from chat_sync.ai_services.run_service import RunService
from chat_sync.ai_services.stream_writer import RunExecutionCancelled, StreamWriter
from chat_sync.auth import resolve_user_from_ticket
from chat_sync.ai_tasks.outbox_tasks import relay_chat_event_outbox
from chat_sync.ai_tasks.run_tasks import run_chat
from chat_sync.ai_runtime.providers.types import ProviderChunk, ProviderRoute
from chat_sync.models import ChatThread
from chat_sync.tests.run_factory import canonical_run_payload


@override_settings(
    CHAT_AI_SERVER_RUNS_ENABLED=True,
    CHAT_AI_RUN_EXECUTOR="disabled",
    CHAT_AI_OUTBOX_IMMEDIATE_RELAY=False,
)
class P2StreamingProjectionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="p2-stream-user")
        self.thread = ChatThread.objects.create(user=self.user, title="P2")
        self.run = RunService.create_run(
            user=self.user,
            thread_id=self.thread.id,
            payload=canonical_run_payload(self.thread.id, content="请回答", client={"platform": "web", "version": "p2", "device_id": "test"}),
            idempotency_key="p2-stream-1",
        ).run
        self.run = RunService.claim_for_execution(run_id=self.run.id, expected_generation=1)

    def test_projects_canonical_events_block_usage_and_terminal_order(self):
        StreamWriter.append_text(run_id=self.run.id, text="你", lease_token=self.run.lease_token)
        StreamWriter.append_text(run_id=self.run.id, text="好", lease_token=self.run.lease_token)
        finished = StreamWriter.finish(
            run_id=self.run.id,
            status=RunStatus.COMPLETED,
            finish_reason="stop",
            lease_token=self.run.lease_token,
            usage={"prompt_tokens": 12, "completion_tokens": 2, "total_tokens": 14, "reasoning_tokens": 1},
            provider_request_id="provider-request-1",
        )

        self.assertEqual(
            list(finished.events.values_list("type", flat=True)),
            [
                "run.queued",
                "run.started",
                "assistant.status",
                "block.created",
                "assistant.status",
                "block.delta",
                "block.delta",
                "block.completed",
                "usage.final",
                "run.completed",
                "run.done",
            ],
        )
        block = finished.assistant_message.blocks.get(kind="text")
        self.assertEqual(block.payload["text"]["_0"], "你好")
        self.assertEqual(block.revision, 3)
        self.assertEqual(block.status, "ready")
        usage = ChatUsageRecord.objects.get(run=finished)
        self.assertEqual((usage.prompt_tokens, usage.completion_tokens, usage.reasoning_tokens), (12, 2, 1))
        finished.refresh_from_db()
        self.assertIsNone(finished.lease_token)
        self.assertEqual(finished.provider_request_id, "provider-request-1")

    def test_stream_write_observes_cancel_request(self):
        RunService.request_cancel(user_id=self.user.id, run_id=self.run.id)
        with self.assertRaises(RunExecutionCancelled):
            StreamWriter.append_text(run_id=self.run.id, text="不应写入", lease_token=self.run.lease_token)
        finished = StreamWriter.finish(run_id=self.run.id, status=RunStatus.COMPLETED, lease_token=self.run.lease_token)
        self.assertEqual(finished.status, RunStatus.CANCELLED)
        self.assertEqual(finished.events.filter(type="run.cancelled").count(), 1)


@override_settings(CHAT_AI_WS_TICKET_TTL_SECONDS=30)
class P2WebSocketTicketTests(TransactionTestCase):
    reset_sequences = True

    def test_ticket_is_short_lived_and_single_use(self):
        user = get_user_model().objects.create_user(username="p2-ticket-user")
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post("/api/v1/ai/chat/ws-tickets/", {}, format="json")
        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertNotIn("token", payload)
        resolved = async_to_sync(resolve_user_from_ticket)(payload["ticket"], payload["websocket_path"])
        replay = async_to_sync(resolve_user_from_ticket)(payload["ticket"], payload["websocket_path"])
        self.assertEqual(resolved.id, user.id)
        self.assertFalse(replay.is_authenticated)


class _ChannelLayer:
    def __init__(self, fail=False):
        self.fail = fail
        self.events = []

    async def group_send(self, group, event):
        if self.fail:
            raise RuntimeError("channel unavailable")
        self.events.append((group, event))


@override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled", CHAT_AI_OUTBOX_IMMEDIATE_RELAY=False)
class P2OutboxTests(TestCase):
    def test_relay_publishes_pending_rows(self):
        user = get_user_model().objects.create_user(username="p2-outbox-user")
        thread = ChatThread.objects.create(user=user, title="P2 outbox")
        RunService.create_run(
            user=user,
            thread_id=thread.id,
            payload=canonical_run_payload(thread.id, content="hello", client={}),
            idempotency_key="p2-outbox-1",
        )
        layer = _ChannelLayer()
        with patch("chat_sync.ai_tasks.outbox_tasks.get_channel_layer", return_value=layer):
            result = relay_chat_event_outbox.run(limit=10)
        self.assertEqual(result["delivered"], 1)
        self.assertEqual(ChatEventOutbox.objects.get().status, ChatEventOutbox.Status.PUBLISHED)
        self.assertEqual(len(layer.events), 1)


class _ProviderGateway:
    async def stream(self, request):
        yield ProviderChunk(text_delta="真实")
        yield ProviderChunk(
            text_delta="回答",
            finish_reason="stop",
            provider_request_id="fake-provider-request",
            usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        )


@override_settings(
    CHAT_AI_SERVER_RUNS_ENABLED=True,
    CHAT_AI_RUN_EXECUTOR="provider",
    CHAT_AI_AGENTIC_TOOLS_ENABLED=False,
    CHAT_AI_OUTBOX_IMMEDIATE_RELAY=False,
)
class P2ProviderTaskIntegrationTests(TransactionTestCase):
    reset_sequences = True

    def test_provider_worker_closes_a_real_text_run(self):
        user = get_user_model().objects.create_user(username="p2-provider-user")
        thread = ChatThread.objects.create(user=user, title="P2 provider")
        run = RunService.create_run(
            user=user,
            thread_id=thread.id,
            payload=canonical_run_payload(thread.id, content="question", client={}),
            idempotency_key="p2-provider-1",
        ).run
        route = ProviderRoute("doubao", "fake-model", "https://provider.test/v1", "secret")
        context = SimpleNamespace(messages=[{"role": "user", "content": "question"}], tool_manifest=[], context_hash="test-hash")
        with (
            patch("chat_sync.ai_tasks.run_tasks.resolve_chat_route", return_value=route),
            patch("chat_sync.ai_tasks.run_tasks.create_chat_gateway", return_value=_ProviderGateway()),
            patch("chat_sync.ai_tasks.run_tasks.build_context_for_run", return_value=context),
        ):
            result = run_chat.run(str(run.id), expected_generation=1, request_id="test-request")

        run.refresh_from_db()
        self.assertEqual(result["status"], RunStatus.COMPLETED)
        self.assertEqual(run.assistant_message.blocks.get(kind="text").payload["text"]["_0"], "真实回答")
        self.assertEqual(run.usage.prompt_tokens, 5)
        self.assertEqual(run.provider_request_id, "fake-provider-request")
        self.assertEqual(run.events.filter(type="run.done").count(), 1)
        self.assertEqual(run.events.filter(type="agent.round.started").count(), 1)
        self.assertEqual(run.events.filter(type="agent.round.completed").count(), 1)
        self.assertFalse(run.assistant_message.blocks.filter(kind="deepThought").exists())
