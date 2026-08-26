from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from chat_sync.models import ChatMessageBlock, ChatThread


class RunApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="run-api-user")
        self.thread = ChatThread.objects.create(user=self.user, title="API run")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def payload(self):
        # v1 content-only input is no longer accepted (CHAT-DATA-026).
        return {
            "client_message_id": str(uuid.uuid4()),
            "content": "hello from api",
            "capability": "chat",
            "client": {"platform": "web", "version": "test", "device_id": "device"},
        }

    def v2_payload(self, *, thread_id=None):
        block_id = uuid.uuid4()
        return {
            "input_message": {
                "thread_id": str(thread_id or self.thread.id),
                "role": "user",
                "client_message_id": str(uuid.uuid4()),
                "blocks": [
                    {
                        "id": str(block_id),
                        "kind": "text",
                        "status": "ready",
                        "revision": 1,
                        "order_key": 1000,
                        "node_role": "timeline",
                        "payload": {"text": {"_0": "hello v2"}},
                    }
                ],
            },
            "run_options": {
                "capability": "chat",
                "client": {"platform": "web", "version": "test", "device_id": "device"},
            },
        }, block_id

    def url(self):
        return f"/api/v1/ai/chat/threads/{self.thread.id}/runs/"

    @override_settings(CHAT_AI_SERVER_RUNS_ENABLED=False)
    def test_create_is_disabled_by_default(self):
        payload, _ = self.v2_payload()
        response = self.client.post(self.url(), payload, format="json", HTTP_IDEMPOTENCY_KEY="api-1")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["msg"], "chat_server_runs_disabled")

    @override_settings(CHAT_AI_SERVER_RUNS_ENABLED=False)
    def test_v1_content_only_is_rejected(self):
        response = self.client.post(self.url(), self.payload(), format="json", HTTP_IDEMPOTENCY_KEY="api-v1")
        self.assertEqual(response.status_code, 400)

    @override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled")
    def test_create_detail_events_and_replay(self):
        payload, _ = self.v2_payload()
        response = self.client.post(self.url(), payload, format="json", HTTP_IDEMPOTENCY_KEY="api-1")
        self.assertEqual(response.status_code, 202)
        run_id = response.data["data"]["run"]["id"]
        replay = self.client.post(self.url(), payload, format="json", HTTP_IDEMPOTENCY_KEY="api-1")
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["data"]["run"]["id"], run_id)

        detail = self.client.get(f"/api/v1/ai/chat/runs/{run_id}/")
        self.assertEqual(detail.status_code, 200)
        events = self.client.get(f"/api/v1/ai/chat/runs/{run_id}/events/?after_sequence=0")
        self.assertEqual(events.status_code, 200)
        self.assertEqual(events.data["data"]["events"][0]["type"], "run.queued")

    @override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled")
    def test_foreign_thread_is_not_disclosed(self):
        other = get_user_model().objects.create_user(username="other-api-user")
        other_thread = ChatThread.objects.create(user=other, title="Other")
        payload, _ = self.v2_payload(thread_id=other_thread.id)
        response = self.client.post(
            f"/api/v1/ai/chat/threads/{other_thread.id}/runs/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="api-foreign",
        )
        self.assertEqual(response.status_code, 404)

    @override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled")
    def test_create_v2_input_message_persists_canonical_blocks(self):
        payload, block_id = self.v2_payload()
        response = self.client.post(self.url(), payload, format="json", HTTP_IDEMPOTENCY_KEY="api-v2")
        self.assertEqual(response.status_code, 202)
        block = ChatMessageBlock.objects.get(id=block_id)
        self.assertEqual(block.kind, "text")
        self.assertEqual(block.node_role, "timeline")
        self.assertEqual(block.payload, {"text": {"_0": "hello v2"}})

    @override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled")
    def test_create_v2_rejects_thread_id_mismatch(self):
        payload, _ = self.v2_payload(thread_id=uuid.uuid4())
        response = self.client.post(self.url(), payload, format="json", HTTP_IDEMPOTENCY_KEY="api-v2-mismatch")
        self.assertEqual(response.status_code, 400)
