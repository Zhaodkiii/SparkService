from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

from chat_sync.ai_runtime.protocols.tool_protocol import BaseTool, ToolDefinition

from .policy import ToolPolicy


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    tool: BaseTool
    policy: ToolPolicy
    schema: dict[str, Any]
    schema_hash: str


class ToolRegistry:
    """Explicit, process-local read-only registry for audited Spark tools."""

    def __init__(self) -> None:
        self._entries: dict[str, RegisteredTool] = {}

    def register(self, tool: BaseTool, policy: ToolPolicy | None = None) -> None:
        definition = tool.get_definition()
        if policy is None:
            import logging

            logging.getLogger("chat_sync.ai.tools").warning(
                "tool_manifest.implicit_server_target tool=%s",
                definition.name,
            )
        resolved_policy = policy or ToolPolicy(name=definition.name)
        if definition.name != resolved_policy.name:
            raise ValueError("tool definition and policy names differ")
        resolved_policy.validate()
        if definition.name in self._entries:
            raise ValueError(f"duplicate tool: {definition.name}")
        schema = definition.to_openai_schema()
        schema_json = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self._entries[definition.name] = RegisteredTool(
            tool=tool,
            policy=resolved_policy,
            schema=schema,
            schema_hash=hashlib.sha256(schema_json.encode("utf-8")).hexdigest(),
        )

    def get(self, name: str) -> RegisteredTool | None:
        return self._entries.get(str(name))

    def list_names(self) -> list[str]:
        return list(self._entries)

    def get_enabled(self, names: Iterable[str]) -> list[RegisteredTool]:
        seen: set[str] = set()
        result: list[RegisteredTool] = []
        for raw in names:
            name = str(raw or "").strip()
            if name in seen:
                continue
            entry = self.get(name)
            if entry is not None:
                result.append(entry)
                seen.add(name)
        return result

    def definitions(self, names: Iterable[str] | None = None) -> list[ToolDefinition]:
        entries = self._entries.values() if names is None else self.get_enabled(names)
        return [entry.tool.get_definition() for entry in entries]

    def schemas(self, names: Iterable[str] | None = None) -> list[dict[str, Any]]:
        entries = self._entries.values() if names is None else self.get_enabled(names)
        return [entry.schema for entry in entries]


def server_tool_entries(registry: ToolRegistry) -> list[RegisteredTool]:
    """Registry entries that are both ``target=server`` and in ``SparkServerToolName``."""
    from .server_names import server_tool_name_values

    allowed = server_tool_name_values()
    result: list[RegisteredTool] = []
    for name in registry.list_names():
        entry = registry.get(name)
        if entry is not None and name in allowed and entry.policy.target == "server":
            result.append(entry)
    return result


def build_server_tool_registry() -> ToolRegistry:
    from .adapters.search_knowledge_bag import SearchKnowledgeBagTool
    from .adapters.ask_user import AskUserTool
    from .adapters.client import (
        FetchEnergyDetailsTool,
        FetchNutritionDetailsTool,
        FetchSleepDetailsTool,
        FetchStepDetailsTool,
        FetchWorkoutDetailsTool,
        GetCurrentLocationTool,
    )
    from .adapters.current_member import CurrentMemberTool
    from .adapters.health_resource import HealthResourceContextTool
    from .adapters.health_sources import HealthSourcesTool
    from .adapters.member_profile import MemberProfileTool
    from .adapters.read_source import ReadSourceTool

    registry = ToolRegistry()
    for tool, policy in (
        (AskUserTool(), ToolPolicy("ask_user", execution_mode="pause", max_result_tokens=800)),
        (SearchKnowledgeBagTool(), ToolPolicy("search_knowledge_bag", required_context=("knowledge_base",), max_result_tokens=1800)),
        (FetchStepDetailsTool(), ToolPolicy("fetch_step_details", target="client", execution_mode="pause", supported_platforms=("ios",), timeout_seconds=600, max_result_tokens=1800)),
        (FetchEnergyDetailsTool(), ToolPolicy("fetch_energy_details", target="client", execution_mode="pause", supported_platforms=("ios",), timeout_seconds=600, max_result_tokens=1800)),
        (FetchNutritionDetailsTool(), ToolPolicy("fetch_nutrition_details", target="client", execution_mode="pause", supported_platforms=("ios",), timeout_seconds=600, max_result_tokens=1800)),
        (FetchSleepDetailsTool(), ToolPolicy("fetch_sleep_details", target="client", execution_mode="pause", supported_platforms=("ios",), timeout_seconds=600, max_result_tokens=1800)),
        (FetchWorkoutDetailsTool(), ToolPolicy("fetch_workout_details", target="client", execution_mode="pause", supported_platforms=("ios",), timeout_seconds=600, max_result_tokens=1800)),
        (GetCurrentLocationTool(), ToolPolicy("get_current_location", target="client", execution_mode="pause", supported_platforms=("ios",), timeout_seconds=600, max_result_tokens=800)),
        (CurrentMemberTool(), ToolPolicy("get_current_member", required_context=("member",), max_result_tokens=800)),
        (MemberProfileTool(), ToolPolicy("query_member_profile", required_context=("member",), max_result_tokens=1600)),
        (HealthSourcesTool(), ToolPolicy("list_member_health_sources", required_context=("member",), max_result_tokens=1800)),
        (HealthResourceContextTool(), ToolPolicy("get_health_resource_context", required_context=("member",), max_result_tokens=2000)),
        (ReadSourceTool(), ToolPolicy("read_source", required_context=("source",), max_result_tokens=2000)),
    ):
        registry.register(tool, policy)
    return registry


__all__ = ["RegisteredTool", "ToolRegistry", "build_server_tool_registry", "server_tool_entries"]
