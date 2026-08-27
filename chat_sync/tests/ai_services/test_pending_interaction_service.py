from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from chat_sync.ai_models import ChatAgentCheckpoint, ChatPendingInteraction, ChatThreadRunLock, ChatToolCall, RunStatus
from chat_sync.ai_services.pending_interaction_service import ASK_USER_SCHEMA_VERSION, PendingInteractionService
from chat_sync.ai_services.run_service import RunService
from chat_sync.contracts import KIND_TOOL_QUESTION_CARDS, payload_kind
from chat_sync.models import ChatThread
from chat_sync.tests.run_factory import canonical_run_payload
from common.exceptions import APIError


@override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled")
class PendingInteractionServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="p5-user")
        self.thread = ChatThread.objects.create(user=self.user, title="p5")
        self.run = RunService.create_run(
            user=self.user,
            thread_id=self.thread.id,
            payload=canonical_run_payload(self.thread.id, content="请分析我的睡眠", client={"platform": "web", "version": "test", "device_id": "web-device"}),
            idempotency_key=str(uuid.uuid4()),
        ).run
        RunService.claim_mock(run_id=self.run.id, expected_generation=1)
        self.tool_call = ChatToolCall.objects.create(
            run=self.run,
            tool_call_id="call_ask_1",
            tool_name="ask_user",
            canonical_name="ask_user",
            arguments={"question": "分析几天？"},
            round_index=0,
            call_index=0,
            status=ChatToolCall.Status.RUNNING,
        )
        self.request_schema = {
            "intro": "需要更多信息",
            "questions": [
                {
                    "id": "q1",
                    "header": "时间范围",
                    "prompt": "分析几天？",
                    "options": [{"label": "7 天"}, {"label": "30 天"}],
                    "multi_select": False,
                    "allow_free_text": True,
                }
            ],
        }

    def _pause(self, schema=None):
        return PendingInteractionService.pause_for_tool(
            run_id=self.run.id,
            tool_call_id=self.tool_call.tool_call_id,
            kind="ask_user",
            request_schema=schema or self.request_schema,
        )

    def _question_block(self):
        return self.run.assistant_message.blocks.get(kind=KIND_TOOL_QUESTION_CARDS, tool_call_id="call_ask_1")

    def test_pause_and_resolve_same_run(self):
        interaction = self._pause()
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, RunStatus.WAITING_FOR_USER_INPUT)
        self.assertEqual(interaction.status, ChatPendingInteraction.Status.PENDING)
        result = PendingInteractionService.resolve(
            user_id=self.user.id,
            public_id=interaction.public_id,
            response={
                "run_id": str(self.run.id),
                "interaction_key": interaction.interaction_key,
                "schema_version": ASK_USER_SCHEMA_VERSION,
                "resolution": "answered",
                "answers": [{"question_id": "q1", "selected_option_indexes": [1], "selected_labels": ["30 天"]}],
            },
            idempotency_key="answer-1",
        )
        self.assertFalse(result.replayed)
        self.run.refresh_from_db()
        self.tool_call.refresh_from_db()
        self.assertEqual(self.run.status, RunStatus.QUEUED)
        self.assertEqual(self.tool_call.status, ChatToolCall.Status.COMPLETED)
        self.assertEqual(ChatThreadRunLock.objects.get(thread=self.thread).active_run_id, self.run.id)

    def test_serialize_dto_v2_fields(self):
        interaction = self._pause()
        data = PendingInteractionService.serialize(interaction)
        self.assertEqual(data["run_id"], str(self.run.id))
        self.assertEqual(data["interaction_id"], str(interaction.public_id))
        self.assertEqual(data["interaction_key"], interaction.interaction_key)
        self.assertEqual(data["tool_call_id"], "call_ask_1")
        self.assertEqual(data["tool_name"], "ask_user")
        self.assertEqual(data["schema_version"], ASK_USER_SCHEMA_VERSION)
        self.assertEqual(data["question_ids"], ["q1"])
        self.assertEqual(data["kind"], "ask_user")
        self.assertIn("request", data)
        self.assertNotIn("id", data)
        self.assertNotIn("schema", data)

    def test_pause_projects_tool_question_cards_not_search_summary(self):
        interaction = self._pause()
        block = self._question_block()
        self.assertEqual(block.status, "pending")
        self.assertEqual(payload_kind(block.payload), KIND_TOOL_QUESTION_CARDS)
        inner = block.payload["tool_question_cards"]["_0"]
        self.assertEqual(inner["interaction_id"], str(interaction.public_id))
        self.assertEqual(inner["run_id"], str(self.run.id))
        self.assertEqual(inner["tool_call_id"], "call_ask_1")
        self.assertEqual(inner["status"], "pending")
        self.assertEqual(inner["question_ids"], ["q1"])
        self.assertNotIn("arguments", str(block.payload))
        self.assertEqual(self.run.assistant_message.blocks.filter(kind="searchSummary", tool_call_id="call_ask_1").count(), 0)
        self.assertEqual(self.run.events.filter(type="interaction.requested").count(), 1)
        self.assertEqual(self.run.events.filter(type="block.created").filter(payload__kind=KIND_TOOL_QUESTION_CARDS).count(), 1)

    def test_resolve_updates_same_block_revision(self):
        interaction = self._pause()
        block = self._question_block()
        block_id = block.id
        first_revision = block.revision
        PendingInteractionService.resolve(
            user_id=self.user.id,
            public_id=interaction.public_id,
            response={"resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [0], "selected_labels": ["7 天"]}]},
            idempotency_key="answer-same-block",
        )
        block.refresh_from_db()
        self.assertEqual(block.id, block_id)
        self.assertGreater(block.revision, first_revision)
        self.assertEqual(block.status, "ready")
        inner = block.payload["tool_question_cards"]["_0"]
        self.assertEqual(inner["status"], "resolved")
        self.assertEqual(self.run.assistant_message.blocks.filter(kind=KIND_TOOL_QUESTION_CARDS, tool_call_id="call_ask_1").count(), 1)
        self.assertEqual(self.run.assistant_message.blocks.filter(kind="searchSummary", tool_call_id="call_ask_1").count(), 0)

    def test_same_response_is_idempotent_and_different_response_conflicts(self):
        interaction = self._pause()
        response = {"resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [0], "selected_labels": ["7 天"]}]}
        first = PendingInteractionService.resolve(user_id=self.user.id, public_id=interaction.public_id, response=response, idempotency_key="same-key")
        self.assertFalse(first.replayed)
        replay = PendingInteractionService.resolve(user_id=self.user.id, public_id=interaction.public_id, response=response, idempotency_key="same-key")
        self.assertTrue(replay.replayed)
        with self.assertRaises(APIError) as caught:
            PendingInteractionService.resolve(
                user_id=self.user.id,
                public_id=interaction.public_id,
                response={"resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [1], "selected_labels": ["30 天"]}]},
                idempotency_key="same-key",
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.code, 40997)

    def test_second_device_loses_with_stable_conflict(self):
        interaction = self._pause()
        PendingInteractionService.resolve(
            user_id=self.user.id,
            public_id=interaction.public_id,
            response={"resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [0], "selected_labels": ["7 天"]}]},
            idempotency_key="device-a",
        )
        with self.assertRaises(APIError) as caught:
            PendingInteractionService.resolve(
                user_id=self.user.id,
                public_id=interaction.public_id,
                response={"resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [1], "selected_labels": ["30 天"]}]},
                idempotency_key="device-b",
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.code, 40998)

    def test_rejects_label_without_matching_index(self):
        interaction = self._pause()
        with self.assertRaises(APIError) as caught:
            PendingInteractionService.resolve(
                user_id=self.user.id,
                public_id=interaction.public_id,
                response={"resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [0], "selected_labels": ["30 天"]}]},
                idempotency_key="bad-label",
            )
        self.assertEqual(caught.exception.status_code, 422)
        with self.assertRaises(APIError):
            PendingInteractionService.resolve(
                user_id=self.user.id,
                public_id=interaction.public_id,
                response={"resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [], "selected_labels": ["7 天"]}]},
                idempotency_key="label-only",
            )

    def test_rejects_unknown_question_and_mismatched_run(self):
        interaction = self._pause()
        with self.assertRaises(APIError):
            PendingInteractionService.resolve(
                user_id=self.user.id,
                public_id=interaction.public_id,
                response={"resolution": "answered", "answers": [{"question_id": "nope", "selected_option_indexes": [0], "selected_labels": ["7 天"]}]},
                idempotency_key="unknown-q",
            )
        with self.assertRaises(APIError) as caught:
            PendingInteractionService.resolve(
                user_id=self.user.id,
                public_id=interaction.public_id,
                response={"run_id": str(uuid.uuid4()), "resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [0], "selected_labels": ["7 天"]}]},
                idempotency_key="wrong-run",
            )
        self.assertEqual(caught.exception.status_code, 422)

    def test_cancel_waiting_run_cancels_interaction_and_block(self):
        interaction = self._pause()
        block = self._question_block()
        block_id = block.id
        RunService.request_cancel(user_id=self.user.id, run_id=self.run.id)
        interaction.refresh_from_db()
        block.refresh_from_db()
        self.run.refresh_from_db()
        self.assertEqual(interaction.status, ChatPendingInteraction.Status.CANCELLED)
        self.assertEqual(self.run.status, RunStatus.CANCELLED)
        self.assertEqual(block.id, block_id)
        self.assertEqual(block.status, "failed")
        self.assertEqual(block.payload["tool_question_cards"]["_0"]["status"], "cancelled")
        self.assertEqual(self.run.events.filter(type="interaction.cancelled").count(), 1)

    def test_expire_due_updates_same_block_and_appends_tool_once(self):
        interaction = self._pause()
        ChatAgentCheckpoint.objects.create(run=self.run, transcript=[{"role": "assistant", "content": "need more"}])
        ChatPendingInteraction.objects.filter(pk=interaction.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        block = self._question_block()
        block_id = block.id
        result = PendingInteractionService.expire_due(limit=10)
        self.assertEqual(result["expired"], 1)
        interaction.refresh_from_db()
        block.refresh_from_db()
        self.run.refresh_from_db()
        self.assertEqual(interaction.status, ChatPendingInteraction.Status.EXPIRED)
        self.assertEqual(self.run.status, RunStatus.QUEUED)
        self.assertEqual(block.id, block_id)
        self.assertEqual(block.payload["tool_question_cards"]["_0"]["status"], "expired")
        checkpoint = ChatAgentCheckpoint.objects.get(run=self.run)
        tool_messages = [item for item in checkpoint.transcript if item.get("role") == "tool"]
        self.assertEqual(len(tool_messages), 1)
        PendingInteractionService.expire_due(limit=10)
        checkpoint.refresh_from_db()
        self.assertEqual(len([item for item in checkpoint.transcript if item.get("role") == "tool"]), 1)

    def test_checkpoint_resume_does_not_duplicate_tool_message(self):
        interaction = self._pause()
        ChatAgentCheckpoint.objects.create(run=self.run, transcript=[])
        PendingInteractionService.resolve(
            user_id=self.user.id,
            public_id=interaction.public_id,
            response={"resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [0], "selected_labels": ["7 天"], "free_text": "secret-note"}]},
            idempotency_key="once",
        )
        checkpoint = ChatAgentCheckpoint.objects.get(run=self.run)
        self.assertEqual(sum(1 for item in checkpoint.transcript if item.get("role") == "tool"), 1)
        PendingInteractionService.resolve(
            user_id=self.user.id,
            public_id=interaction.public_id,
            response={"resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [0], "selected_labels": ["7 天"], "free_text": "secret-note"}]},
            idempotency_key="once",
        )
        checkpoint.refresh_from_db()
        self.assertEqual(sum(1 for item in checkpoint.transcript if item.get("role") == "tool"), 1)

    def test_expired_resolve_returns_410(self):
        interaction = self._pause()
        ChatPendingInteraction.objects.filter(pk=interaction.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(APIError) as caught:
            PendingInteractionService.resolve(
                user_id=self.user.id,
                public_id=interaction.public_id,
                response={"resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [0], "selected_labels": ["7 天"]}]},
                idempotency_key="too-late",
            )
        self.assertEqual(caught.exception.status_code, 410)
        self.assertEqual(caught.exception.code, 41094)

    def test_ask_user_claim_is_not_supported(self):
        from accounts.models import AccountDeviceSession, TrustedDevice

        interaction = self._pause()
        device = TrustedDevice.objects.create(
            user=self.user,
            device_id="web-1",
            platform="web",
            bundle_id="com.spark.web",
        )
        AccountDeviceSession.objects.create(
            user=self.user,
            trusted_device=device,
            device_id="web-1",
            bundle_id="com.spark.web",
            status=AccountDeviceSession.Status.ACTIVE,
        )
        with self.assertRaises(APIError) as caught:
            PendingInteractionService.claim(
                user_id=self.user.id,
                public_id=interaction.public_id,
                device_id="web-1",
                platform="web",
                version="1.0",
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.code, 40995)

    def test_client_tool_claim_heartbeat_and_reclaim_after_lease_expiry(self):
        from accounts.models import AccountDeviceSession, TrustedDevice

        thread = ChatThread.objects.create(user=self.user, title="p5-client")
        run = RunService.create_run(
            user=self.user,
            thread_id=thread.id,
            payload=canonical_run_payload(thread.id, content="步数", client={"platform": "ios", "version": "test", "device_id": "ios-1"}),
            idempotency_key=str(uuid.uuid4()),
        ).run
        RunService.claim_mock(run_id=run.id, expected_generation=1)
        client_call = ChatToolCall.objects.create(
            run=run,
            tool_call_id="call_steps_1",
            tool_name="fetch_step_details",
            canonical_name="fetch_step_details",
            arguments={"days": 7},
            round_index=0,
            call_index=0,
            status=ChatToolCall.Status.RUNNING,
            target="client",
            execution_mode="pause",
        )
        interaction = PendingInteractionService.pause_for_tool(
            run_id=run.id,
            tool_call_id=client_call.tool_call_id,
            kind="client_tool",
            request_schema={"name": "fetch_step_details", "arguments": {"days": 7}},
            required_platform="ios",
            required_capability="healthkit.steps",
        )
        device = TrustedDevice.objects.create(
            user=self.user,
            device_id="ios-1",
            platform="ios",
            bundle_id="com.spark.ios",
        )
        AccountDeviceSession.objects.create(
            user=self.user,
            trusted_device=device,
            device_id="ios-1",
            bundle_id="com.spark.ios",
            status=AccountDeviceSession.Status.ACTIVE,
        )
        claimed, token = PendingInteractionService.claim(
            user_id=self.user.id,
            public_id=interaction.public_id,
            device_id="ios-1",
            platform="ios",
            version="1.0",
        )
        self.assertEqual(claimed.status, ChatPendingInteraction.Status.CLAIMED)
        first_expiry = claimed.claim_expires_at
        heartbeated = PendingInteractionService.heartbeat(
            user_id=self.user.id,
            public_id=interaction.public_id,
            device_id="ios-1",
            claim_token=token,
        )
        self.assertGreaterEqual(heartbeated.claim_expires_at, first_expiry)
        with self.assertRaises(APIError) as already:
            PendingInteractionService.claim(
                user_id=self.user.id,
                public_id=interaction.public_id,
                device_id="ios-1",
                platform="ios",
                version="1.0",
            )
        self.assertEqual(already.exception.code, 40994)
        ChatPendingInteraction.objects.filter(pk=interaction.pk).update(claim_expires_at=timezone.now() - timedelta(seconds=1))
        result = PendingInteractionService.expire_due(limit=10)
        self.assertGreaterEqual(result["reclaimed"], 1)
        interaction.refresh_from_db()
        self.assertEqual(interaction.status, ChatPendingInteraction.Status.PENDING)
        self.assertEqual(interaction.claimed_by_device, "")

    def test_metrics_emitted_without_free_text(self):
        interaction = self._pause()
        with self.assertLogs("chat_sync.ai.metrics", level="INFO") as logs:
            PendingInteractionService.resolve(
                user_id=self.user.id,
                public_id=interaction.public_id,
                response={"resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [0], "selected_labels": ["7 天"], "free_text": "secret-note"}]},
                idempotency_key="metrics-1",
            )
        joined = "\n".join(logs.output)
        self.assertIn("chat_interaction_total", joined)
        self.assertIn("chat_interaction_resume_total", joined)
        self.assertIn("chat_interaction_wait_seconds", joined)
        self.assertNotIn("secret-note", joined)
