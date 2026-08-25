from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from chat_sync.ai_models import ChatPendingInteraction, ChatThreadRunLock, ChatToolCall, RunStatus
from chat_sync.ai_services.pending_interaction_service import PendingInteractionService
from chat_sync.ai_services.run_service import RunService
from chat_sync.models import ChatThread


@override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled")
class PendingInteractionServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="p5-user")
        self.thread = ChatThread.objects.create(user=self.user, title="p5")
        self.run = RunService.create_run(
            user=self.user,
            thread_id=self.thread.id,
            payload={
                "client_message_id": uuid.uuid4(),
                "content": "请分析我的睡眠",
                "capability": "chat",
                "client": {"platform": "web", "version": "test", "device_id": "web-device"},
            },
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

    def test_pause_and_resolve_same_run(self):
        interaction = PendingInteractionService.pause_for_tool(
            run_id=self.run.id,
            tool_call_id=self.tool_call.tool_call_id,
            kind="ask_user",
            request_schema={
                "intro": "需要更多信息",
                "questions": [{"id": "q1", "prompt": "分析几天？", "options": [{"label": "7 天"}, {"label": "30 天"}], "multi_select": False, "allow_free_text": False}],
            },
        )
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, RunStatus.WAITING_FOR_USER_INPUT)
        self.assertEqual(interaction.status, ChatPendingInteraction.Status.PENDING)
        result = PendingInteractionService.resolve(
            user_id=self.user.id,
            public_id=interaction.public_id,
            response={"resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [1], "selected_labels": ["30 天"]}]},
            idempotency_key="answer-1",
        )
        self.assertFalse(result.replayed)
        self.run.refresh_from_db()
        self.tool_call.refresh_from_db()
        self.assertEqual(self.run.status, RunStatus.QUEUED)
        self.assertEqual(self.tool_call.status, ChatToolCall.Status.COMPLETED)
        self.assertEqual(ChatThreadRunLock.objects.get(thread=self.thread).active_run_id, self.run.id)

    def test_same_response_is_idempotent_and_different_response_conflicts(self):
        interaction = PendingInteractionService.pause_for_tool(
            run_id=self.run.id,
            tool_call_id=self.tool_call.tool_call_id,
            kind="ask_user",
            request_schema={"questions": [{"id": "q1", "prompt": "继续吗？", "options": [{"label": "是"}], "allow_free_text": False}]},
        )
        response = {"resolution": "answered", "answers": [{"question_id": "q1", "selected_option_indexes": [0], "selected_labels": ["是"]}]}
        first = PendingInteractionService.resolve(user_id=self.user.id, public_id=interaction.public_id, response=response, idempotency_key="same-key")
        self.assertFalse(first.replayed)
        replay = PendingInteractionService.resolve(user_id=self.user.id, public_id=interaction.public_id, response=response, idempotency_key="same-key")
        self.assertTrue(replay.replayed)

    def test_cancel_waiting_run_cancels_interaction(self):
        interaction = PendingInteractionService.pause_for_tool(
            run_id=self.run.id,
            tool_call_id=self.tool_call.tool_call_id,
            kind="ask_user",
            request_schema={"questions": [{"id": "q1", "prompt": "继续吗？"}]},
        )
        RunService.request_cancel(user_id=self.user.id, run_id=self.run.id)
        interaction.refresh_from_db()
        self.run.refresh_from_db()
        self.assertEqual(interaction.status, ChatPendingInteraction.Status.CANCELLED)
        self.assertEqual(self.run.status, RunStatus.CANCELLED)
