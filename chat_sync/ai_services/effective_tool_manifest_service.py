"""Unified Effective Tool Manifest for CHAT-AI-030.

Scenario binding is the candidate source. Registry, server enum, policy,
context, model capability and thread preferences filter the Run snapshot.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from django.conf import settings

from chat_sync.ai_runtime.tools.composition import compose_enabled_tools, manifest_entries
from chat_sync.ai_runtime.tools.public_projector import P4_SERVER_TOOL_NAMES
from chat_sync.ai_runtime.tools.reasons import ToolFilterReason, map_composition_reason
from chat_sync.ai_runtime.tools.registry import ToolRegistry, build_server_tool_registry
from chat_sync.ai_runtime.tools.server_names import SparkServerToolName, server_tool_name_values


USER_TOGGLEABLE_TOOLS: frozenset[str] = frozenset(P4_SERVER_TOOL_NAMES)
ASK_USER_TOOL = SparkServerToolName.ASK_USER.value


@dataclass(frozen=True, slots=True)
class ToolFeatureFlags:
    agentic_tools_enabled: bool = False
    waiting_enabled: bool = False
    ask_user_enabled: bool = False
    client_tools_enabled: bool = False


@dataclass(frozen=True, slots=True)
class EffectiveToolManifest:
    scenario_key: str
    resolved_model: str
    source_server_tool_scenarios: tuple[str, ...]
    effective_tools: tuple[dict[str, Any], ...]
    filtered_tools: tuple[dict[str, str], ...]
    manifest_hash: str
    generated_at: str


def feature_flags_from_settings() -> ToolFeatureFlags:
    waiting = bool(getattr(settings, "CHAT_AI_WAITING_ENABLED", False))
    return ToolFeatureFlags(
        agentic_tools_enabled=bool(getattr(settings, "CHAT_AI_AGENTIC_TOOLS_ENABLED", False)),
        waiting_enabled=waiting,
        ask_user_enabled=bool(getattr(settings, "CHAT_AI_ASK_USER_ENABLED", False)),
        client_tools_enabled=waiting and bool(getattr(settings, "CHAT_AI_CLIENT_TOOLS_ENABLED", False)),
    )


def normalize_tool_names(raw: Iterable[str] | None) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for item in raw or ():
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def compute_manifest_hash(entries: Iterable[dict[str, Any]]) -> str:
    payload = [
        {
            "name": str(item.get("name") or ""),
            "version": str(item.get("version") or ""),
            "schema_hash": str(item.get("schema_hash") or ""),
        }
        for item in entries
        if isinstance(item, dict) and item.get("name")
    ]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_client_spark_tool(name: str) -> bool:
    from ai_config.models import SparkToolName

    client_names = {item.value for item in SparkToolName}
    return name in client_names and name not in server_tool_name_values()


def _filter_item(name: str, reason: str) -> dict[str, str]:
    return {"name": name, "reason": reason}


def _classify_configured_name(name: str, registry: ToolRegistry) -> str | None:
    server_names = server_tool_name_values()
    if name not in server_names:
        if _is_client_spark_tool(name):
            return ToolFilterReason.CLIENT_ONLY
        return ToolFilterReason.NOT_REGISTERED
    entry = registry.get(name)
    if entry is None:
        return ToolFilterReason.EXECUTOR_MISSING
    if entry.policy.target != "server":
        return ToolFilterReason.CLIENT_ONLY
    schema = entry.schema if isinstance(entry.schema, dict) else {}
    if not schema:
        return ToolFilterReason.INVALID_SCHEMA
    return None


def resolve_binding_for_scenario(scenario_key: str | None = None):
    from chat_sync.ai_runtime.providers.factory import resolve_scenario_binding

    return resolve_scenario_binding(scenario_key)


def build_effective_tool_manifest(
    *,
    capability: str = "chat",
    scenario_key: str = "chat",
    resolved_model: str = "",
    model_supports_tools: bool = False,
    member_id: int | None = None,
    source_ids: Iterable[str] = (),
    knowledge_base_ids: Iterable[str] = (),
    capability_owned_tools: Iterable[str] = (),
    auto_context_tools: Iterable[str] = (),
    deferred_active_names: Iterable[str] = (),
    thread_enabled_tools: Iterable[str] = (),
    feature_flags: ToolFeatureFlags | None = None,
    registry: ToolRegistry | None = None,
    binding=None,
    client_platform: str = "",
    client_tool_names: Iterable[str] = (),
) -> EffectiveToolManifest:
    flags = feature_flags or feature_flags_from_settings()
    registry = registry or build_server_tool_registry()
    if binding is None:
        binding = resolve_binding_for_scenario(scenario_key)
    model_name = resolved_model or (binding.model.name if binding is not None else "")
    source_names = normalize_tool_names(getattr(binding, "server_tool_scenarios", None) if binding is not None else [])

    filtered: list[dict[str, str]] = []
    skip_user_disabled: set[str] = set()
    candidates: list[str] = []
    seen: set[str] = set()

    def _reject(name: str, reason: str) -> None:
        if name not in {item["name"] for item in filtered}:
            filtered.append(_filter_item(name, reason))

    def _accept(name: str, *, immune_to_user_disable: bool = False) -> None:
        if name in seen:
            if immune_to_user_disable:
                skip_user_disabled.add(name)
            return
        reason = _classify_configured_name(name, registry)
        if reason is not None:
            _reject(name, reason)
            return
        seen.add(name)
        candidates.append(name)
        if immune_to_user_disable:
            skip_user_disabled.add(name)

    for name in source_names:
        _accept(name)

    for name in normalize_tool_names(capability_owned_tools):
        _accept(name, immune_to_user_disable=True)
    for name in normalize_tool_names(auto_context_tools):
        _accept(name, immune_to_user_disable=True)
    for name in normalize_tool_names(deferred_active_names):
        _accept(name, immune_to_user_disable=True)

    ask_user_allowed = flags.waiting_enabled and flags.ask_user_enabled
    remaining: list[str] = []
    enabled_set = set(normalize_tool_names(thread_enabled_tools))
    for name in candidates:
        if name == ASK_USER_TOOL and not ask_user_allowed:
            _reject(name, ToolFilterReason.FEATURE_DISABLED)
            continue
        if name in USER_TOGGLEABLE_TOOLS and name not in skip_user_disabled and name not in enabled_set:
            _reject(name, ToolFilterReason.USER_DISABLED)
            continue
        remaining.append(name)

    composition = compose_enabled_tools(
        registry=registry,
        requested=remaining,
        member_id=member_id,
        source_ids=source_ids,
        knowledge_base_ids=knowledge_base_ids,
        model_supports_tools=model_supports_tools,
        feature_enabled=flags.agentic_tools_enabled,
        client_tools_enabled=flags.client_tools_enabled,
        client_platform=client_platform,
        client_tool_names=client_tool_names,
    )
    for item in composition.unavailable:
        _reject(str(item.get("name") or ""), map_composition_reason(str(item.get("reason") or "")))

    effective_names = list(composition.effective_names)
    effective_names.sort()
    entries = manifest_entries(registry, effective_names)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return EffectiveToolManifest(
        scenario_key=str(scenario_key or "chat"),
        resolved_model=str(model_name or ""),
        source_server_tool_scenarios=tuple(source_names),
        effective_tools=tuple(entries),
        filtered_tools=tuple(filtered),
        manifest_hash=compute_manifest_hash(entries),
        generated_at=generated_at,
    )


def evaluate_public_catalog_tools(
    *,
    member_id: int | None,
    has_sources: bool,
    knowledge_base_ids: Iterable[str],
    model_supports_tools: bool,
    thread_enabled_tools: Iterable[str],
    feature_flags: ToolFeatureFlags | None = None,
    registry: ToolRegistry | None = None,
) -> list[dict[str, Any]]:
    """Project the P4 public catalog using the same filter pipeline as a Run."""
    flags = feature_flags or feature_flags_from_settings()
    registry = registry or build_server_tool_registry()
    source_ids = ("catalog-source",) if has_sources else ()
    enabled_set = set(normalize_tool_names(thread_enabled_tools))
    rows: list[dict[str, Any]] = []
    for name in P4_SERVER_TOOL_NAMES:
        entry = registry.get(name)
        version = entry.policy.version if entry else "v1"
        required_context = list(entry.policy.required_context) if entry else []
        target = entry.policy.target if entry else "server"
        reason: str | None = None
        if entry is None or entry.policy.target != "server":
            reason = ToolFilterReason.EXECUTOR_MISSING if entry is None else ToolFilterReason.CLIENT_ONLY
        else:
            composition = compose_enabled_tools(
                registry=registry,
                requested=[name],
                member_id=member_id,
                source_ids=source_ids,
                knowledge_base_ids=knowledge_base_ids,
                model_supports_tools=model_supports_tools,
                feature_enabled=flags.agentic_tools_enabled,
                client_tools_enabled=False,
                client_platform="web",
                client_tool_names=(),
            )
            if composition.unavailable:
                reason = map_composition_reason(composition.unavailable[0]["reason"])
        rows.append(
            {
                "name": name,
                "version": version,
                "target": target,
                "enabled": name in enabled_set,
                "available": reason is None,
                "unavailable_reason": reason,
                "requires": required_context,
            }
        )
    return rows


__all__ = [
    "ASK_USER_TOOL",
    "EffectiveToolManifest",
    "ToolFeatureFlags",
    "USER_TOGGLEABLE_TOOLS",
    "build_effective_tool_manifest",
    "compute_manifest_hash",
    "evaluate_public_catalog_tools",
    "feature_flags_from_settings",
    "normalize_tool_names",
    "resolve_binding_for_scenario",
]
