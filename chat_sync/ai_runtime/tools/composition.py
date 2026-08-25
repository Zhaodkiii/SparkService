from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .registry import ToolRegistry


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
    model_supports_tools: bool = False,
    feature_enabled: bool = False,
    client_tools_enabled: bool = False,
    client_platform: str = "",
    client_tool_names: Iterable[str] = (),
) -> ToolComposition:
    requested_names = list(dict.fromkeys(str(name).strip() for name in requested if str(name).strip()))
    if not feature_enabled:
        return ToolComposition((), tuple({"name": name, "reason": "feature_disabled"} for name in requested_names))
    if not model_supports_tools:
        return ToolComposition((), tuple({"name": name, "reason": "model_unsupported"} for name in requested_names))
    allowed: list[str] = []
    unavailable: list[dict[str, str]] = []
    source_set = set(source_ids)
    client_names = set(client_tool_names)
    for name in requested_names:
        entry = registry.get(name)
        if entry is None:
            unavailable.append({"name": name, "reason": "not_registered"})
            continue
        if entry.policy.target == "client":
            if not client_tools_enabled:
                unavailable.append({"name": name, "reason": "client_tools_disabled"})
                continue
            if entry.policy.supported_platforms and client_platform not in entry.policy.supported_platforms:
                unavailable.append({"name": name, "reason": "platform_unsupported"})
                continue
            if name not in client_names:
                unavailable.append({"name": name, "reason": "client_capability_missing"})
                continue
        if "member" in entry.policy.required_context and member_id is None:
            unavailable.append({"name": name, "reason": "member_required"})
            continue
        if "source" in entry.policy.required_context and not source_set:
            unavailable.append({"name": name, "reason": "source_required"})
            continue
        allowed.append(name)
    return ToolComposition(tuple(allowed), tuple(unavailable))


def manifest_entries(registry: ToolRegistry, names: Iterable[str]) -> list[dict[str, Any]]:
    return [
        {
            "name": entry.policy.name,
            "version": entry.policy.version,
            "target": entry.policy.target,
            "policy": {
                "risk": entry.policy.risk,
                "side_effect": entry.policy.side_effect,
                "timeout_seconds": entry.policy.timeout_seconds,
                "max_result_tokens": entry.policy.max_result_tokens,
                "supported_platforms": list(entry.policy.supported_platforms),
            },
            "schema": entry.schema,
            "schema_hash": entry.schema_hash,
        }
        for entry in registry.get_enabled(names)
    ]


__all__ = ["ToolComposition", "compose_enabled_tools", "manifest_entries"]
