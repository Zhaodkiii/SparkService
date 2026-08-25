from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from chat_sync.ai_models import ChatDeferredToolState
from chat_sync.ai_runtime.capabilities import build_capability_registry
from chat_sync.ai_runtime.tools.deferred import validate_load_names
from chat_sync.ai_services.deferred_tool_service import DeferredToolService
from chat_sync.ai_services.run_service import RunService
from chat_sync.models import ChatThread


@override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled")
class P6CapabilityDeferredTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="p6-capability")
        self.thread = ChatThread.objects.create(user=self.user, title="p6")
        self.run = RunService.create_run(
            user=self.user,
            thread_id=self.thread.id,
            payload={
                "client_message_id": uuid.uuid4(),
                "content": "hello",
                "capability": "chat",
                "references": [],
                "attachments": [],
                "client": {"platform": "web", "client_tools": []},
            },
            idempotency_key=str(uuid.uuid4()),
        ).run

    def test_manifest_is_versioned_and_hashed(self):
        manifest = build_capability_registry().require("chat", "v1")
        self.assertEqual(manifest.key, "chat@v1")
        self.assertEqual(len(manifest.manifest_hash), 64)

    def test_exact_load_and_revoke_persist_state(self):
        result = DeferredToolService.load(
            user_id=self.user.id,
            thread_id=self.thread.id,
            run_id=self.run.id,
            names=["ask_user"],
        )
        self.assertEqual(result["loaded"], ["ask_user"])
        state = ChatDeferredToolState.objects.get(thread=self.thread, tool_name="ask_user")
        self.assertEqual(state.capability, "chat")
        self.assertTrue(state.loaded_at)
        revoked = DeferredToolService.revoke(
            user_id=self.user.id,
            thread_id=self.thread.id,
            names=["ask_user"],
        )
        self.assertEqual(len(revoked), 1)
        state.refresh_from_db()
        self.assertTrue(state.revoked_at)

    def test_loader_rejects_wildcards_and_more_than_eight_names(self):
        with self.assertRaises(ValueError):
            validate_load_names(["*"])
        with self.assertRaises(ValueError):
            validate_load_names([f"tool_{index}" for index in range(9)])
