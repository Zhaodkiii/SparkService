from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from chat_sync.ai_models import ChatRunEvent, ChatThreadRunLock, RunStatus
from chat_sync.ai_services.run_service import RunService
from chat_sync.models import ChatThread
from chat_sync.tests.run_factory import canonical_run_payload


@override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled")
class RunServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="run-service-user")
        self.thread = ChatThread.objects.create(user=self.user, title="Run test")
        self.default_client_message_id = uuid.uuid4()

    def payload(self, content="hello"):
        client_message_id = self.default_client_message_id if content == "hello" else uuid.uuid4()
        return canonical_run_payload(self.thread.id, content=content, client_message_id=client_message_id)

    def create(self, key="key-1", content="hello"):
        return RunService.create_run(
            user=self.user,
            thread_id=self.thread.id,
            payload=self.payload(content),
            idempotency_key=key,
        )

    def test_create_is_atomic_and_writes_queued_event_and_outbox(self):
        result = self.create()

        self.assertFalse(result.replayed)
        run = result.run
        self.assertEqual(run.status, RunStatus.QUEUED)
        self.assertEqual(run.last_sequence, 1)
        self.assertEqual(run.user_message.role, "user")
        self.assertEqual(run.assistant_message.delivery_state, "pending")
        event = ChatRunEvent.objects.get(run=run, sequence=1)
        self.assertEqual(event.type, "run.queued")
        self.assertEqual(event.outbox.status, "pending")
        self.assertEqual(ChatThreadRunLock.objects.get(thread=self.thread).active_run_id, run.id)

    def test_same_idempotency_key_replays_without_new_rows(self):
        first = self.create()
        second = RunService.create_run(
            user=self.user,
            thread_id=self.thread.id,
            payload=self.payload(),
            idempotency_key="key-1",
        )

        self.assertTrue(second.replayed)
        self.assertEqual(first.run.id, second.run.id)
        self.assertEqual(self.user.chat_ai_runs.count(), 1)
        self.assertEqual(self.thread.messages.count(), 2)
        self.assertEqual(first.run.events.count(), 1)

    def test_same_idempotency_key_with_different_request_conflicts(self):
        self.create(content="first")
        with self.assertRaisesMessage(Exception, "chat_idempotency_conflict"):
            self.create(content="second")

    def test_active_thread_rejects_second_run(self):
        self.create()
        with self.assertRaisesMessage(Exception, "chat_run_already_active"):
            self.create(key="key-2")

    def test_queued_cancel_writes_terminal_and_releases_lock(self):
        run = self.create().run
        cancelled = RunService.request_cancel(user_id=self.user.id, run_id=run.id)
        cancelled.refresh_from_db()

        self.assertEqual(cancelled.status, RunStatus.CANCELLED)
        self.assertEqual(list(cancelled.events.values_list("type", flat=True)), ["run.queued", "run.cancelled", "run.done"])
        self.assertEqual(ChatThreadRunLock.objects.get(thread=self.thread).active_run_id, None)
        self.assertEqual(cancelled.assistant_message.delivery_state, "failed")

    def test_mock_claim_then_finalize_and_regenerate_preserves_old_run(self):
        old = self.create().run
        claimed = RunService.claim_mock(run_id=old.id, expected_generation=1)
        self.assertEqual(claimed.status, RunStatus.RUNNING)
        finished = RunService.finalize_mock(run_id=old.id, status=RunStatus.COMPLETED)
        self.assertEqual(finished.status, RunStatus.COMPLETED)

        regenerated = RunService.regenerate(
            user=self.user,
            run_id=old.id,
            idempotency_key="regenerate-1",
        ).run
        self.assertEqual(regenerated.status, RunStatus.QUEUED)
        self.assertEqual(regenerated.user_message_id, old.user_message_id)
        self.assertEqual(regenerated.regenerated_from_run_id, old.id)
        old.refresh_from_db()
        self.assertEqual(old.status, RunStatus.COMPLETED)
        self.assertEqual(list(regenerated.events.values_list("sequence", flat=True)), [1])
