from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from chat_sync.ai_runtime.tools.reasons import ToolFilterReason
from chat_sync.ai_runtime.tools.registry import build_server_tool_registry, server_tool_entries
from chat_sync.ai_runtime.tools.server_names import SparkServerToolName, server_tool_name_values
from chat_sync.ai_runtime.tools.server_tool_config import prepare_server_tool_scenarios
from chat_sync.ai_services.effective_tool_manifest_service import (
    ToolFeatureFlags,
    build_effective_tool_manifest,
    compute_manifest_hash,
)


def _binding(names, model="doubao-pro"):
    return SimpleNamespace(server_tool_scenarios=list(names), model=SimpleNamespace(name=model))


def _flags(**overrides):
    values = dict(
        agentic_tools_enabled=True,
        waiting_enabled=True,
        ask_user_enabled=True,
        client_tools_enabled=False,
    )
    values.update(overrides)
    return ToolFeatureFlags(**values)


class EffectiveToolManifestTests(SimpleTestCase):
    def test_server_enum_matches_registry_executors(self):
        registry = build_server_tool_registry()
        entries = {entry.policy.name for entry in server_tool_entries(registry)}
        self.assertEqual(entries, set(server_tool_name_values()))
        self.assertNotIn("get_current_location", entries)
        self.assertEqual(SparkServerToolName.ASK_USER.value, "ask_user")

    def test_unknown_and_client_tools_are_filtered(self):
        manifest = build_effective_tool_manifest(
            binding=_binding(["read_source", "unknown_tool", "get_current_location"]),
            model_supports_tools=True,
            source_ids=["src-1"],
            thread_enabled_tools=["read_source"],
            feature_flags=_flags(),
            registry=build_server_tool_registry(),
        )
        names = {item["name"] for item in manifest.effective_tools}
        reasons = {item["name"]: item["reason"] for item in manifest.filtered_tools}
        self.assertIn("read_source", names)
        self.assertEqual(reasons["unknown_tool"], ToolFilterReason.NOT_REGISTERED)
        self.assertEqual(reasons["get_current_location"], ToolFilterReason.CLIENT_ONLY)
        self.assertNotIn("get_current_location", names)

    def test_missing_context_marks_unavailable_instead_of_blocking(self):
        manifest = build_effective_tool_manifest(
            binding=_binding(["read_source", "ask_user"]),
            model_supports_tools=True,
            source_ids=(),
            thread_enabled_tools=["read_source"],
            feature_flags=_flags(),
            registry=build_server_tool_registry(),
        )
        names = {item["name"] for item in manifest.effective_tools}
        reasons = {item["name"]: item["reason"] for item in manifest.filtered_tools}
        self.assertNotIn("read_source", names)
        self.assertEqual(reasons["read_source"], ToolFilterReason.CONTEXT_MISSING)
        self.assertIn("ask_user", names)

    def test_user_can_only_disable_toggleable_tools_inside_whitelist(self):
        manifest = build_effective_tool_manifest(
            binding=_binding(["read_source", "ask_user"]),
            model_supports_tools=True,
            source_ids=["src-1"],
            thread_enabled_tools=[],
            feature_flags=_flags(),
            registry=build_server_tool_registry(),
        )
        names = {item["name"] for item in manifest.effective_tools}
        reasons = {item["name"]: item["reason"] for item in manifest.filtered_tools}
        self.assertNotIn("read_source", names)
        self.assertEqual(reasons["read_source"], ToolFilterReason.USER_DISABLED)
        self.assertIn("ask_user", names)

    def test_enabled_tools_outside_whitelist_are_ignored(self):
        manifest = build_effective_tool_manifest(
            binding=_binding(["ask_user"]),
            model_supports_tools=True,
            thread_enabled_tools=["read_source", "query_member_profile"],
            feature_flags=_flags(),
            registry=build_server_tool_registry(),
        )
        names = {item["name"] for item in manifest.effective_tools}
        self.assertEqual(names, {"ask_user"})

    def test_model_unsupported_filters_all_remaining_tools(self):
        manifest = build_effective_tool_manifest(
            binding=_binding(["ask_user"]),
            model_supports_tools=False,
            feature_flags=_flags(),
            registry=build_server_tool_registry(),
        )
        self.assertEqual(manifest.effective_tools, ())
        reasons = {item["name"]: item["reason"] for item in manifest.filtered_tools}
        self.assertEqual(reasons["ask_user"], ToolFilterReason.MODEL_UNSUPPORTED)

    def test_auto_context_tool_skips_user_disabled(self):
        manifest = build_effective_tool_manifest(
            binding=_binding([]),
            model_supports_tools=True,
            knowledge_base_ids=["kb-1"],
            auto_context_tools=["search_knowledge_bag"],
            thread_enabled_tools=[],
            feature_flags=_flags(),
            registry=build_server_tool_registry(),
        )
        names = {item["name"] for item in manifest.effective_tools}
        self.assertIn("search_knowledge_bag", names)

    def test_manifest_hash_is_stable(self):
        kwargs = dict(
            binding=_binding(["ask_user", "read_source"]),
            model_supports_tools=True,
            source_ids=["src-1"],
            thread_enabled_tools=["read_source"],
            feature_flags=_flags(),
            registry=build_server_tool_registry(),
        )
        first = build_effective_tool_manifest(**kwargs)
        second = build_effective_tool_manifest(**kwargs)
        self.assertEqual(first.manifest_hash, second.manifest_hash)
        self.assertEqual(first.manifest_hash, compute_manifest_hash(first.effective_tools))
        self.assertEqual(list(first.source_server_tool_scenarios), ["ask_user", "read_source"])

    def test_prepare_server_tool_scenarios_rejects_client_and_unknown(self):
        names, error, _offending = prepare_server_tool_scenarios(["read_source", "read_source", "ask_user"])
        self.assertIsNone(error)
        self.assertEqual(names, ["ask_user", "read_source"])
        _, error, offending = prepare_server_tool_scenarios(["get_current_location"])
        self.assertEqual(error, "server_tool_client_only_not_allowed")
        self.assertEqual(offending, "get_current_location")
        _, error, offending = prepare_server_tool_scenarios(["not_a_tool"])
        self.assertEqual(error, "server_tool_unknown_name")
        self.assertEqual(offending, "not_a_tool")
