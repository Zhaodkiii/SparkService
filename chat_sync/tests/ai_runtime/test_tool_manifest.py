from __future__ import annotations

import pytest

from chat_sync.ai_runtime.tools.composition import compose_enabled_tools, manifest_entries, provider_tool_schemas
from chat_sync.ai_runtime.tools.policy import ToolPolicy
from chat_sync.ai_runtime.tools.registry import ToolRegistry, build_server_tool_registry


def test_tool_policy_rejects_invalid_target_and_execution_mode():
    with pytest.raises(ValueError):
        ToolPolicy(name="ask_user", target="browser").validate()  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ToolPolicy(name="ask_user", execution_mode="defer").validate()  # type: ignore[arg-type]


def test_manifest_entries_include_target_and_execution_mode():
    registry = build_server_tool_registry()
    entries = {item["name"]: item for item in manifest_entries(registry, ["ask_user", "fetch_step_details", "read_source"])}
    ask_user = entries["ask_user"]
    assert ask_user["target"] == "server"
    assert ask_user["execution_mode"] == "pause"
    assert ask_user["policy_version"] == "v1"
    assert ask_user["required_context"] == []
    assert "description" in ask_user
    assert ask_user["schema"]["type"] == "function"
    steps = entries["fetch_step_details"]
    assert steps["target"] == "client"
    assert steps["execution_mode"] == "pause"
    assert steps["supported_platforms"] == ["ios"]
    assert steps["timeout_seconds"] == 600
    read_source = entries["read_source"]
    assert read_source["target"] == "server"
    assert read_source["execution_mode"] == "immediate"
    assert read_source["required_context"] == ["source"]


def test_web_run_filters_client_tools_without_executor():
    registry = build_server_tool_registry()
    composition = compose_enabled_tools(
        registry=registry,
        requested=["ask_user", "read_source", "fetch_step_details", "get_current_location"],
        member_id=1,
        source_ids=["src-1"],
        model_supports_tools=True,
        feature_enabled=True,
        client_tools_enabled=True,
        client_platform="web",
        client_tool_names=[],
    )
    assert "ask_user" in composition.effective_names
    assert "read_source" in composition.effective_names
    assert "fetch_step_details" not in composition.effective_names
    assert "get_current_location" not in composition.effective_names
    reasons = {item["name"]: item["reason"] for item in composition.unavailable}
    assert reasons["fetch_step_details"] == "platform_unsupported"


def test_ios_capability_missing_filters_healthkit_tools():
    registry = build_server_tool_registry()
    composition = compose_enabled_tools(
        registry=registry,
        requested=["fetch_step_details"],
        member_id=1,
        model_supports_tools=True,
        feature_enabled=True,
        client_tools_enabled=True,
        client_platform="ios",
        client_tool_names=[],
    )
    assert composition.effective_names == ()
    assert composition.unavailable[0]["reason"] == "client_capability_missing"


def test_provider_schemas_strip_spark_metadata():
    registry = build_server_tool_registry()
    entries = manifest_entries(registry, ["ask_user", "fetch_step_details"])
    schemas = provider_tool_schemas(entries)
    assert all(item["type"] == "function" for item in schemas)
    dumped = str(schemas)
    assert "execution_mode" not in dumped
    assert "supported_platforms" not in dumped
    assert "required_permissions" not in dumped
    assert "schema_hash" not in dumped
    assert "target" not in dumped
    assert names == {"ask_user", "fetch_step_details"}


def test_frozen_manifest_is_not_recomputed_from_live_registry():
    frozen = [
        {
            "name": "ask_user",
            "description": "frozen",
            "schema": {"type": "function", "function": {"name": "ask_user", "description": "frozen", "parameters": {"type": "object"}}},
            "target": "server",
            "execution_mode": "pause",
        }
    ]
    schemas = provider_tool_schemas(frozen)
    assert schemas == [
        {
            "type": "function",
            "function": {"name": "ask_user", "description": "frozen", "parameters": {"type": "object"}},
        }
    ]
    dumped = str(schemas)
    assert "execution_mode" not in dumped
    assert "target" not in dumped


def test_implicit_server_target_warns(caplog):
    from chat_sync.ai_runtime.tools.adapters.ask_user import AskUserTool

    registry = ToolRegistry()
    with caplog.at_level("WARNING", logger="chat_sync.ai.tools"):
        registry.register(AskUserTool())
    assert any("implicit_server_target" in message for message in caplog.messages)
    entry = registry.get("ask_user")
    assert entry is not None
    assert entry.policy.target == "server"
