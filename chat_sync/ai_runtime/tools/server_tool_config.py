"""Validation for ``AIScenarioModelBinding.server_tool_scenarios``."""

from __future__ import annotations

from typing import Any

from ai_config.models import SparkToolName

from .registry import build_server_tool_registry
from .server_names import SparkServerToolName, server_tool_name_values


def prepare_server_tool_scenarios(value: Any) -> tuple[list[str], str | None, str | None]:
    """Normalize and validate a server tool name list.

    Returns ``(names, error_code, offending_name)``.
    """
    if value is None:
        return [], None, None
    if not isinstance(value, list):
        return [], "server_tool_scenarios_must_be_string_array", None
    server_names = server_tool_name_values()
    client_only = {item.value for item in SparkToolName} - server_names
    registry = build_server_tool_registry()
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if raw is None:
            continue
        name = str(raw).strip()
        if not name:
            continue
        if name in seen:
            continue
        if name in client_only:
            return [], "server_tool_client_only_not_allowed", name
        if name not in server_names:
            return [], "server_tool_unknown_name", name
        entry = registry.get(name)
        if entry is None or entry.tool is None:
            return [], "server_tool_executor_missing", name
        if entry.policy.target != "server":
            return [], "server_tool_client_only_not_allowed", name
        seen.add(name)
        cleaned.append(name)
    cleaned.sort()
    return cleaned, None, None


def list_admin_server_tool_options() -> list[dict[str, Any]]:
    registry = build_server_tool_registry()
    rows: list[dict[str, Any]] = []
    for item in SparkServerToolName:
        entry = registry.get(item.value)
        has_executor = entry is not None and entry.tool is not None and entry.policy.target == "server"
        policy = entry.policy if entry is not None else None
        rows.append(
            {
                "value": item.value,
                "label": item.label,
                "version": policy.version if policy else "v1",
                "risk": policy.risk if policy else "read_only",
                "side_effect": policy.side_effect if policy else "none",
                "has_executor": has_executor,
                "required_permissions": list(policy.required_permissions) if policy else [],
                "required_context": list(policy.required_context) if policy else [],
                "enabled": has_executor,
            }
        )
    return rows


__all__ = ["list_admin_server_tool_options", "prepare_server_tool_scenarios"]
