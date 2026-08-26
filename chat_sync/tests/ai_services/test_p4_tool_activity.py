from __future__ import annotations

import json
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from chat_sync.ai_models import ChatToolCall
from chat_sync.ai_runtime.protocols.tool_protocol import ToolResult
from chat_sync.ai_runtime.tools.dispatcher import ToolDispatchItem
from chat_sync.ai_runtime.tools.public_projector import (
    public_args,
    public_display_name,
    public_error,
    public_result_preview,
    safe_source_refs,
)
from chat_sync.ai_runtime.tools.registry import build_server_tool_registry
from chat_sync.ai_runtime.tools.scoped_registry import ScopedToolRegistry
from chat_sync.ai_services.run_service import RunService
from chat_sync.ai_services.tool_state_service import (
    converge_cancelled_tool_calls,
    mark_tool_started,
    record_tool_progress,
    record_tool_requests,
    record_tool_results,
)
from chat_sync.models import ChatThread
from chat_sync.tests.run_factory import canonical_run_payload


def _tool_event_payloads(run, event_type: str) -> list[dict]:
    return [event.payload for event in run.events.filter(type=event_type).order_by("sequence")]


@override_settings(
    CHAT_AI_SERVER_RUNS_ENABLED=True,
    CHAT_AI_RUN_EXECUTOR="disabled",
    CHAT_AI_OUTBOX_IMMEDIATE_RELAY=False,
)
class P4ToolStateServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="p4-tool-user")
        self.thread = ChatThread.objects.create(user=self.user, title="P4", member_id=None)
        self.run = RunService.create_run(
            user=self.user,
            thread_id=self.thread.id,
            payload=canonical_run_payload(self.thread.id, content="请回答", client={"platform": "web", "version": "p4", "device_id": "test"}),
            idempotency_key="p4-tool-1",
        ).run
        self.run = RunService.claim_for_execution(run_id=self.run.id, expected_generation=1)
        self.registry = ScopedToolRegistry(build_server_tool_registry(), ["query_member_profile", "get_current_member"])

    def _request_call(self, *, name="query_member_profile", call_id="call_01", round_index=0, arguments=None):
        rows = record_tool_requests(
            self.run.id,
            round_index,
            [{"id": call_id, "name": name, "arguments": arguments or {"sections": ["allergies"]}}],
            self.registry,
        )
        return rows[0]

    def test_requested_emits_safe_activity_and_block_event(self):
        row = self._request_call()
        events = _tool_event_payloads(self.run, "tool.call.requested")
        self.assertEqual(len(events), 1)
        activity = events[0]["activity"]
        self.assertEqual(activity["tool_call_id"], "call_01")
        self.assertEqual(activity["display_name"], "读取健康档案")
        self.assertEqual(activity["status"], "requested")
        self.assertEqual(activity["revision"], 1)
        self.assertEqual(activity["display_args"], {"sections": ["过敏史"]})
        # Raw arguments / hashes / execution keys never leak.
        self.assertNotIn("arguments", activity)
        self.assertNotIn("arguments_hash", activity)
        self.assertNotIn("execution_key", activity)
        block_created = _tool_event_payloads(self.run, "block.created")
        self.assertEqual(block_created[-1]["kind"], "tool")
        payload = block_created[-1]["block"]["payload"]
        inner = payload["tool"]["_0"]
        self.assertEqual(inner["name"], "读取健康档案")
        self.assertEqual(json.loads(inner["invocation_arguments"]["sections"]), ["过敏史"])
        self.assertNotIn("arguments", payload)
        self.assertEqual(row.status, ChatToolCall.Status.REQUESTED)

    def test_started_running_lifecycle(self):
        self._request_call()
        mark_tool_started(self.run.id, "call_01")
        row = ChatToolCall.objects.get(run=self.run, tool_call_id="call_01")
        self.assertEqual(row.status, ChatToolCall.Status.RUNNING)
        self.assertIsNotNone(row.started_at)
        started = _tool_event_payloads(self.run, "tool.call.started")
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0]["status"], "running")
        self.assertEqual(started[0]["revision"], 2)
        updated = _tool_event_payloads(self.run, "block.updated")
        self.assertEqual(updated[-1]["status"], "streaming")
        self.assertEqual(updated[-1]["revision"], 2)
        self.assertEqual(updated[-1]["kind"], "tool")

    def test_progress_emits_transient_patch(self):
        self._request_call()
        mark_tool_started(self.run.id, "call_01")
        record_tool_progress(self.run.id, "call_01", "正在检索健康档案…", 50)
        progress = _tool_event_payloads(self.run, "tool.call.progress")
        self.assertEqual(len(progress), 1)
        self.assertEqual(progress[0]["progress_message"], "正在检索健康档案…")
        self.assertEqual(progress[0]["progress_percent"], 50)
        self.assertEqual(progress[0]["revision"], 2)
        self.assertEqual(progress[0]["tool_call_id"], "call_01")

    def test_progress_ignored_after_terminal(self):
        self._request_call()
        mark_tool_started(self.run.id, "call_01")
        record_tool_results(
            self.run.id,
            [
                ToolDispatchItem(
                    call_id="call_01",
                    name="query_member_profile",
                    arguments={"sections": ["allergies"]},
                    result=ToolResult(content="ok"),
                )
            ],
        )
        record_tool_progress(self.run.id, "call_01", "过晚的进度", 99)
        self.assertEqual(_tool_event_payloads(self.run, "tool.call.progress"), [])

    def test_result_emits_terminal_activity_and_tool_result_block(self):
        self._request_call()
        mark_tool_started(self.run.id, "call_01")
        record_tool_results(
            self.run.id,
            [
                ToolDispatchItem(
                    call_id="call_01",
                    name="query_member_profile",
                    arguments={"sections": ["allergies"]},
                    result=ToolResult(
                        content="allergies: 青霉素\nchronic_conditions: 高血压",
                        sources=[{"source_id": "member_profile:42", "type": "member_profile", "content_hash": "secret", "url": "https://internal"}],
                    ),
                )
            ],
        )
        results = _tool_event_payloads(self.run, "tool.result")
        self.assertEqual(len(results), 1)
        activity = results[0]["activity"]
        self.assertEqual(activity["status"], "completed")
        self.assertEqual(activity["revision"], 3)
        self.assertEqual(activity["result_preview"], "已读取 1 个健康档案分区")
        self.assertEqual(activity["display_args"], {"sections": ["过敏史"]})
        # Raw observation never leaks into the activity.
        self.assertNotIn("青霉素", str(activity))
        self.assertNotIn("高血压", str(activity))
        self.assertEqual(activity["source_refs"], [{"source_id": "member_profile:42", "type": "member_profile"}])
        # toolResult block carries the safe projection only, projected as a
        # toolPresentation searchSummary card.
        result_block = self.run.assistant_message.blocks.get(kind="searchSummary")
        summary = result_block.payload["search_summary"]["_0"]
        self.assertEqual(summary["provider_name"], "读取健康档案")
        self.assertEqual(summary["query"], "已读取 1 个健康档案分区")
        self.assertNotIn("content", result_block.payload)
        self.assertNotIn("青霉素", str(result_block.payload))
        self.assertEqual(result_block.tool_call_id, "call_01")

    def test_failed_result_maps_error_without_message(self):
        self._request_call(name="get_current_member", call_id="call_02")
        record_tool_results(
            self.run.id,
            [
                ToolDispatchItem(
                    call_id="call_02",
                    name="get_current_member",
                    arguments={},
                    result=ToolResult(content="成员资料不可用或无权访问。", success=False, metadata={"error_code": "tool_permission_denied"}),
                )
            ],
        )
        activity = _tool_event_payloads(self.run, "tool.result")[0]["activity"]
        self.assertEqual(activity["status"], "failed")
        self.assertEqual(activity["error"], {"code": "tool_unavailable", "message_key": "tool_unavailable", "retryable": False})
        self.assertIsNone(activity["result_preview"])

    def test_round_encoded_order_keys_do_not_collide_across_rounds(self):
        # Mimic the real flow: one batch per round with parallel calls.
        record_tool_requests(
            self.run.id,
            0,
            [
                {"id": "r0a", "name": "query_member_profile", "arguments": {"sections": ["allergies"]}},
                {"id": "r0b", "name": "query_member_profile", "arguments": {"sections": ["allergies"]}},
            ],
            self.registry,
        )
        record_tool_requests(
            self.run.id,
            1,
            [{"id": "r1a", "name": "query_member_profile", "arguments": {"sections": ["allergies"]}}],
            self.registry,
        )
        call_blocks = self.run.assistant_message.blocks.filter(kind="tool").order_by("order_key")
        keys = [(block.tool_call_id, int(block.order_key)) for block in call_blocks]
        self.assertEqual(keys, [("r0a", 1800), ("r0b", 1801), ("r1a", 1900)])

    def test_converge_cancelled_tool_calls(self):
        self._request_call(call_id="call_x")
        self._request_call(call_id="call_y")
        record_tool_results(
            self.run.id,
            [
                ToolDispatchItem(
                    call_id="call_y",
                    name="query_member_profile",
                    arguments={"sections": []},
                    result=ToolResult(content="ok"),
                )
            ],
        )
        converged = converge_cancelled_tool_calls(self.run.id)
        self.assertEqual(converged, 1)
        self.assertEqual(ChatToolCall.objects.get(run=self.run, tool_call_id="call_x").status, ChatToolCall.Status.CANCELLED)
        self.assertEqual(ChatToolCall.objects.get(run=self.run, tool_call_id="call_y").status, ChatToolCall.Status.COMPLETED)
        cancelled = _tool_event_payloads(self.run, "tool.call.cancelled")
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0]["tool_call_id"], "call_x")
        self.assertEqual(cancelled[0]["activity"]["status"], "cancelled")

    def test_duplicate_result_references_original(self):
        self._request_call(call_id="orig")
        self._request_call(call_id="dup")
        record_tool_results(
            self.run.id,
            [
                ToolDispatchItem(
                    call_id="orig",
                    name="query_member_profile",
                    arguments={"sections": ["allergies"]},
                    result=ToolResult(content="ok"),
                )
            ],
        )
        record_tool_results(
            self.run.id,
            [
                ToolDispatchItem(
                    call_id="dup",
                    name="query_member_profile",
                    arguments={"sections": ["allergies"]},
                    result=ToolResult(content="本轮已执行相同工具调用，复用已有结果。", success=False, metadata={"error_code": "duplicate_tool_call", "duplicate_of": "orig"}),
                    duplicate_of="orig",
                )
            ],
        )
        activity = _tool_event_payloads(self.run, "tool.result")[-1]["activity"]
        self.assertEqual(activity["duplicate_of"], "orig")
        self.assertEqual(activity["result_preview"], "已复用相同请求的结果")


class P4PublicProjectorTests(TestCase):
    def test_args_allowlist(self):
        self.assertEqual(public_args("get_current_member", {"anything": "secret"}), {})
        self.assertEqual(
            public_args("query_member_profile", {"sections": ["allergies"], "injected": "x"}),
            {"sections": ["过敏史"]},
        )
        self.assertEqual(public_args("read_source", {"source_id": "health_exam_report:42"}), {"source_id": "体检报告"})
        self.assertEqual(public_args("unknown_tool", {"a": 1}), {})

    def test_result_preview(self):
        self.assertEqual(public_result_preview("get_current_member", success=True, arguments={}), "已确认当前成员")
        self.assertEqual(public_result_preview("query_member_profile", success=True, arguments={"sections": ["allergies", "chronic_conditions"]}), "已读取 2 个健康档案分区")
        self.assertEqual(
            public_result_preview("list_member_health_sources", success=True, arguments={}, source_refs=[{}, {}, {}]),
            "找到 3 项可用资料",
        )
        self.assertIsNone(public_result_preview("query_member_profile", success=False, arguments={}))

    def test_error_projection_hides_existence(self):
        denied = public_error("tool_permission_denied")
        missing = public_error("tool_resource_not_found")
        self.assertEqual(denied, missing)
        self.assertEqual(denied["message_key"], "tool_unavailable")
        timeout = public_error("tool_timeout")
        self.assertEqual(timeout["message_key"], "tool_timeout")
        self.assertTrue(timeout["retryable"])

    def test_safe_source_refs_strip_untrusted_fields(self):
        refs = safe_source_refs([{"source_id": "a:1", "type": "member_profile", "title": "健康档案", "url": "https://evil", "signed_url": "https://signed"}])
        self.assertEqual(refs, [{"source_id": "a:1", "type": "member_profile", "title": "健康档案"}])

    def test_display_name_falls_back_safely(self):
        self.assertEqual(public_display_name("query_member_profile"), "读取健康档案")
        self.assertEqual(public_display_name("mcp_unknown"), "服务工具")


@override_settings(CHAT_AI_AGENTIC_TOOLS_ENABLED=False, CHAT_AI_OUTBOX_IMMEDIATE_RELAY=False)
class P4ToolCatalogTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="p4-catalog-user")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_catalog_feature_disabled(self):
        thread = ChatThread.objects.create(user=self.user, title="T")
        response = self.client.get(f"/api/v1/ai/chat/threads/{thread.id}/tools/")
        self.assertEqual(response.status_code, 200)
        tools = response.json()["data"]["tools"]
        self.assertEqual(len(tools), 5)
        self.assertTrue(all(tool["available"] is False for tool in tools))
        self.assertTrue(all(tool["unavailable_reason"] == "feature_disabled" for tool in tools))
        names = {tool["name"] for tool in tools}
        self.assertEqual(
            names,
            {"get_current_member", "query_member_profile", "list_member_health_sources", "get_health_resource_context", "read_source"},
        )
        self.assertNotIn("ask_user", names)

    @override_settings(CHAT_AI_AGENTIC_TOOLS_ENABLED=True)
    def test_catalog_member_required_reason(self):
        thread = ChatThread.objects.create(user=self.user, title="T", member_id=None)
        response = self.client.get(f"/api/v1/ai/chat/threads/{thread.id}/tools/")
        tools = response.json()["data"]["tools"]
        get_member = next(tool for tool in tools if tool["name"] == "get_current_member")
        # Feature on but no model binding exists in the test DB.
        self.assertFalse(get_member["available"])
        self.assertIn(get_member["unavailable_reason"], {"model_unsupported", "feature_disabled"})

    def test_preferences_reject_unknown_tool_names(self):
        thread = ChatThread.objects.create(user=self.user, title="T")
        response = self.client.patch(
            f"/api/v1/ai/chat/threads/{thread.id}/preferences/",
            {"revision": 1, "enabled_tools": ["ask_user", "fetch_step_details"]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], 40092)

    def test_preferences_accepts_catalog_tools(self):
        thread = ChatThread.objects.create(user=self.user, title="T")
        response = self.client.patch(
            f"/api/v1/ai/chat/threads/{thread.id}/preferences/",
            {"revision": 1, "enabled_tools": ["query_member_profile", "read_source"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["enabled_tools"], ["query_member_profile", "read_source"])
