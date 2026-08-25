"""Safe short-catalog and exact-name loading primitives.

The model sees descriptions from this module, never provider supplied JSON
schemas. Full schemas are resolved only after authorization succeeds.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .registry import RegisteredTool, ToolRegistry

MAX_CATALOG_ITEMS = 64
MAX_CATALOG_DESCRIPTION = 240
MAX_LOAD_ITEMS = 8
TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _clean_description(value: str) -> str:
    value = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    return " ".join(value.split())[:MAX_CATALOG_DESCRIPTION]


def short_catalog(registry: ToolRegistry, names: Iterable[str] | None = None) -> list[dict[str, Any]]:
    entries = registry.get_enabled(names) if names is not None else [registry.get(name) for name in registry.list_names()]
    result: list[dict[str, Any]] = []
    for entry in entries[:MAX_CATALOG_ITEMS]:
        if entry is None:
            continue
        result.append(
            {
                "name": entry.policy.name,
                "version": entry.policy.version,
                "description": _clean_description(entry.tool.get_definition().description),
                "target": entry.policy.target,
                "risk": entry.policy.risk,
                "required_context": list(entry.policy.required_context),
                "schema_hash": entry.schema_hash,
                "loadable": True,
            }
        )
    return result


def validate_load_names(names: Iterable[str]) -> list[str]:
    normalized = list(dict.fromkeys(str(name or "").strip() for name in names))
    if not normalized or len(normalized) > MAX_LOAD_ITEMS:
        raise ValueError(f"load_tools accepts 1-{MAX_LOAD_ITEMS} exact names")
    if any(not TOOL_NAME_RE.fullmatch(name) for name in normalized):
        raise ValueError("load_tools only accepts canonical exact tool names")
    return normalized


def loaded_schemas(registry: ToolRegistry, names: Iterable[str]) -> list[dict[str, Any]]:
    return [entry.schema for entry in registry.get_enabled(validate_load_names(names))]


__all__ = ["MAX_CATALOG_ITEMS", "MAX_LOAD_ITEMS", "short_catalog", "validate_load_names", "loaded_schemas"]
