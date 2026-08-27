from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .observability import emit_metric
from .policy import ToolManifestEntry
from .registry import RegisteredTool, ToolRegistry


@dataclass(frozen=True, slots=True)
class ToolComposition:
    effective_names: tuple[str, ...]
    unavailable: tuple[dict[str, str], ...]


def compose_enabled_tools(
    *,
    registry: ToolRegistry,
    requested: Iterable[str],
    member_id: int | None,
    source_ids: Iterable[str] = (),
    knowledge_base_ids: Iterable[str] = (),
    model_supports_tools: bool = False,
    feature_enabled: bool = False,
    client_tools_enabled: bool = False,
    client_platform: str = "",
    client_tool_names: Iterable[str] = (),
) -> ToolComposition:
    requested_names = list(dict.fromkeys(str(name).strip() for name in requested if str(name).strip()))
    if not feature_enabled:
        for name in requested_names:
            emit_metric("chat_tool_filtered_total", target="unknown", reason="feature_disabled", platform=client_platform or "unknown", tool=name)
        return ToolComposition((), tuple({"name": name, "reason": "feature_disabled"} for name in requested_names))
    if not model_supports_tools:
        for name in requested_names:
            emit_metric("chat_tool_filtered_total", target="unknown", reason="model_unsupported", platform=client_platform or "unknown", tool=name)
        return ToolComposition((), tuple({"name": name, "reason": "model_unsupported"} for name in requested_names))
    allowed: list[str] = []
    unavailable: list[dict[str, str]] = []
    source_set = set(source_ids)
    knowledge_set = {str(item) for item in knowledge_base_ids if str(item).strip()}
    client_names = set(client_tool_names)
    for name in requested_names:
        entry = registry.get(name)
        if entry is None:
            unavailable.append({"name": name, "reason": "not_registered"})
            emit_metric("chat_tool_filtered_total", target="unknown", reason="not_registered", platform=client_platform or "unknown", tool=name)
            continue
        target = entry.policy.target
        if target == "client":
            if not client_tools_enabled:
                unavailable.append({"name": name, "reason": "client_tools_disabled"})
                emit_metric("chat_tool_filtered_total", target=target, reason="client_tools_disabled", platform=client_platform or "unknown", tool=name)
                continue
            if entry.policy.supported_platforms and client_platform not in entry.policy.supported_platforms:
                unavailable.append({"name": name, "reason": "platform_unsupported"})
                emit_metric("chat_tool_filtered_total", target=target, reason="platform_unsupported", platform=client_platform or "unknown", tool=name)
                continue
            if name not in client_names:
                unavailable.append({"name": name, "reason": "client_capability_missing"})
                emit_metric("chat_tool_filtered_total", target=target, reason="client_capability_missing", platform=client_platform or "unknown", tool=name)
                continue
        if "member" in entry.policy.required_context and member_id is None:
            unavailable.append({"name": name, "reason": "member_required"})
            emit_metric("chat_tool_filtered_total", target=target, reason="member_required", platform=client_platform or "unknown", tool=name)
            continue
        if "source" in entry.policy.required_context and not source_set:
            unavailable.append({"name": name, "reason": "source_required"})
            emit_metric("chat_tool_filtered_total", target=target, reason="source_required", platform=client_platform or "unknown", tool=name)
            continue
        if "knowledge_base" in entry.policy.required_context and not knowledge_set:
            unavailable.append({"name": name, "reason": "knowledge_base_required"})
            emit_metric("chat_tool_filtered_total", target=target, reason="knowledge_base_required", platform=client_platform or "unknown", tool=name)
            continue
        allowed.append(name)
        emit_metric("chat_tool_manifest_total", target=target, tool=name, outcome="offered")
    return ToolComposition(tuple(allowed), tuple(unavailable))


def manifest_entry(entry: RegisteredTool) -> ToolManifestEntry:
    schema = entry.schema if isinstance(entry.schema, dict) else {}
    function = schema.get("function") if isinstance(schema.get("function"), dict) else {}
    parameters = function.get("parameters") if isinstance(function.get("parameters"), dict) else {"type": "object", "properties": {}}
    description = str(function.get("description") or entry.tool.get_definition().description or "")
    return ToolManifestEntry(
        name=entry.policy.name,
        version=entry.policy.version,
        description=description,
        parameters=parameters,
        schema=schema,
        schema_hash=entry.schema_hash,
        policy_version=entry.policy.version,
        target=entry.policy.target,
        execution_mode=entry.policy.execution_mode,
        supported_platforms=entry.policy.supported_platforms,
        required_permissions=entry.policy.required_permissions,
        required_context=entry.policy.required_context,
        risk=entry.policy.risk,
        side_effect=entry.policy.side_effect,
        timeout_seconds=entry.policy.timeout_seconds,
        max_result_tokens=entry.policy.max_result_tokens,
        max_attempts=entry.policy.max_attempts,
    )


def manifest_entries(registry: ToolRegistry, names: Iterable[str]) -> list[dict[str, Any]]:
    return [manifest_entry(entry).to_dict() for entry in registry.get_enabled(names)]


def provider_tool_schemas(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """OpenAI-compatible function schemas with Spark metadata stripped."""
    schemas: list[dict[str, Any]] = []
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        schema = raw.get("schema") if isinstance(raw.get("schema"), dict) else {}
        function = schema.get("function") if isinstance(schema.get("function"), dict) else {}
        name = str(function.get("name") or raw.get("name") or "")
        if not name:
            continue
        parameters = function.get("parameters") if isinstance(function.get("parameters"), dict) else raw.get("parameters")
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(function.get("description") or raw.get("description") or ""),
                    "parameters": parameters if isinstance(parameters, dict) else {"type": "object", "properties": {}},
                },
            }
        )
    return schemas


__all__ = [
    "ToolComposition",
    "compose_enabled_tools",
    "manifest_entry",
    "manifest_entries",
    "provider_tool_schemas",
]
