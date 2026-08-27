from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from chat_sync.ai_models import ChatTurnContextSnapshot
from chat_sync.ai_services.context.context_builder import build_context_for_run
from chat_sync.ai_services.run_service import RunService
from chat_sync.models import ChatThread
from chat_sync.tests.run_factory import canonical_run_payload


@override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled")
class RunToolManifestApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="run-tools-user")
        self.thread = ChatThread.objects.create(user=self.user, title="tools")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_pending_snapshot_returns_empty_manifest(self):
        run = RunService.create_run(
            user=self.user,
            thread_id=self.thread.id,
            payload=canonical_run_payload(self.thread.id, content="hello"),
            idempotency_key=str(uuid.uuid4()),
        ).run
        response = self.client.get(f"/api/v1/ai/chat/runs/{run.id}/tools/")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["build_status"], "pending")
        self.assertEqual(data["effective_tools"], [])
        self.assertEqual(data["manifest_hash"], "")

    def test_ready_snapshot_returns_frozen_fields(self):
        run = RunService.create_run(
            user=self.user,
            thread_id=self.thread.id,
            payload=canonical_run_payload(self.thread.id, content="hello"),
            idempotency_key=str(uuid.uuid4()),
        ).run
        build_context_for_run(run.id)
        snapshot = ChatTurnContextSnapshot.objects.get(run=run)
        snapshot.tool_manifest = [{"name": "ask_user", "version": "v1", "execution_mode": "pause"}]
        snapshot.tool_manifest_source = ["ask_user", "read_source"]
        snapshot.tool_manifest_filtered = [{"name": "read_source", "reason": "user_disabled"}]
        snapshot.tool_manifest_hash = "abc123"
        snapshot.save()
        response = self.client.get(f"/api/v1/ai/chat/runs/{run.id}/tools/")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["source_server_tool_scenarios"], ["ask_user", "read_source"])
        self.assertEqual(data["effective_tools"][0]["name"], "ask_user")
        self.assertEqual(data["filtered_tools"][0]["reason"], "user_disabled")
        self.assertEqual(data["manifest_hash"], "abc123")

    def test_foreign_run_is_hidden(self):
        other = get_user_model().objects.create_user(username="other-tools-user")
        other_thread = ChatThread.objects.create(user=other, title="other")
        run = RunService.create_run(
            user=other,
            thread_id=other_thread.id,
            payload=canonical_run_payload(other_thread.id, content="hello"),
            idempotency_key=str(uuid.uuid4()),
        ).run
        response = self.client.get(f"/api/v1/ai/chat/runs/{run.id}/tools/")
        self.assertEqual(response.status_code, 404)
