from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from chat_sync.ai_models import RunStatus
from chat_sync.ai_services.run_service import RunService
from chat_sync.ai_tasks.run_tasks import run_chat
from chat_sync.models import ChatThread
from chat_sync.tests.run_factory import canonical_run_payload


@override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled")
class MockRunTaskTests(TestCase):
    def test_mock_task_is_idempotent_and_emits_single_done(self):
        user = get_user_model().objects.create_user(username="mock-task-user")
        thread = ChatThread.objects.create(user=user, title="Task")
        result = RunService.create_run(
            user=user,
            thread_id=thread.id,
            payload=canonical_run_payload(thread.id, content="mock", client={}),
            idempotency_key="mock-1",
        )

        with self.settings(CHAT_AI_RUN_EXECUTOR="mock", CHAT_AI_MOCK_OUTCOME="success"):
            task_result = run_chat.run(str(result.run.id), expected_generation=1)
            duplicate = run_chat.run(str(result.run.id), expected_generation=1)

        result.run.refresh_from_db()
        self.assertEqual(task_result["status"], RunStatus.COMPLETED)
        self.assertEqual(duplicate["status"], "noop")
        self.assertEqual(result.run.status, RunStatus.COMPLETED)
        self.assertEqual(result.run.events.filter(type="run.done").count(), 1)
