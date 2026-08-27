from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from chat_sync.ai_models import ChatThreadPreferences, ChatTurnContextSnapshot
from chat_sync.ai_services.context.context_builder import build_context_for_run
from chat_sync.ai_services.run_service import RunService
from chat_sync.models import ChatThread
from chat_sync.tests.run_factory import canonical_run_payload


@override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled")
class ContextBuilderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="context-user")
        self.thread = ChatThread.objects.create(user=self.user, title="context")

    def _run(self, content="hello", **extra):
        payload = canonical_run_payload(
            self.thread.id,
            content=content,
            client={"platform": "web", "version": "test", "device_id": "context-device"},
            **extra,
        )
        return RunService.create_run(user=self.user, thread_id=self.thread.id, payload=payload, idempotency_key=str(uuid.uuid4())).run

    def test_builds_stable_messages_and_snapshot(self):
        run = self._run("请总结一下")
        context = build_context_for_run(run.id)
        self.assertEqual(context.messages[-1]["content"], "请总结一下")
        self.assertEqual(context.messages[0]["role"], "system")
        snapshot = ChatTurnContextSnapshot.objects.get(run=run)
        self.assertEqual(snapshot.build_status, "ready")
        self.assertEqual(snapshot.snapshot_hash, context.context_hash)
        built_at = snapshot.built_at
        self.assertEqual(build_context_for_run(run.id).context_hash, context.context_hash)
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.built_at, built_at)

    def test_context_parent_excludes_sibling_history(self):
        first = self._run("first")
        from chat_sync.ai_services.run_service import RunService as Service

        Service.claim_mock(run_id=first.id, expected_generation=1)
        Service.finalize_mock(run_id=first.id, status="completed")
        second = self._run("second", context_parent_message_id=first.assistant_message_id)
        context = build_context_for_run(second.id)
        contents = [item["content"] for item in context.messages]
        self.assertIn("first", contents)
        self.assertEqual(contents[-1], "second")

    def test_preferences_revision_is_frozen_into_run(self):
        prefs = ChatThreadPreferences.objects.create(thread=self.thread)
        prefs.language = "en"
        prefs.revision = 2
        prefs.save()
        run = self._run("hello", preferences_revision=2)
        prefs.language = "zh-CN"
        prefs.revision = 3
        prefs.save()
        context = build_context_for_run(run.id)
        self.assertIn("en", context.messages[0]["content"])

    def test_tool_manifest_is_frozen_across_rebuilds(self):
        from unittest.mock import patch

        run = self._run("hello")
        build_context_for_run(run.id)
        snapshot = ChatTurnContextSnapshot.objects.get(run=run)
        snapshot.tool_manifest = [{"name": "frozen_tool", "target": "server", "execution_mode": "immediate"}]
        snapshot.save(update_fields=["tool_manifest"])
        with patch("chat_sync.ai_services.context.context_builder._persist_snapshot"):
            second = build_context_for_run(run.id)
        self.assertEqual(
            list(second.tool_manifest),
            [{"name": "frozen_tool", "target": "server", "execution_mode": "immediate"}],
        )

    @override_settings(
        CHAT_AI_AGENTIC_TOOLS_ENABLED=True,
        CHAT_AI_WAITING_ENABLED=True,
        CHAT_AI_ASK_USER_ENABLED=True,
    )
    def test_snapshot_stores_manifest_source_filtered_and_hash(self):
        from unittest.mock import patch

        from chat_sync.ai_services.effective_tool_manifest_service import EffectiveToolManifest

        frozen = EffectiveToolManifest(
            scenario_key="chat",
            resolved_model="doubao-pro",
            source_server_tool_scenarios=("ask_user",),
            effective_tools=({"name": "ask_user", "version": "v1", "schema_hash": "abc"},),
            filtered_tools=({"name": "read_source", "reason": "user_disabled"},),
            manifest_hash="deadbeef",
            generated_at="2026-08-27T10:00:00Z",
        )
        with patch(
            "chat_sync.ai_services.context.context_builder.build_effective_tool_manifest",
            return_value=frozen,
        ):
            run = self._run("hello")
            build_context_for_run(run.id)
        snapshot = ChatTurnContextSnapshot.objects.get(run=run)
        self.assertEqual(snapshot.tool_manifest_hash, "deadbeef")
        self.assertEqual(snapshot.tool_manifest_source, ["ask_user"])
        self.assertEqual(snapshot.tool_manifest_filtered, [{"name": "read_source", "reason": "user_disabled"}])
        rebuilt = build_context_for_run(run.id)
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.tool_manifest_hash, "deadbeef")
        self.assertEqual(list(rebuilt.tool_manifest), list(frozen.effective_tools))
