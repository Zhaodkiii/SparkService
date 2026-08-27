"""P4 Public Tool Catalog.

Computes, per user/thread/model/context, which read-only server tools the Web
may display and toggle. The catalog is an allowlist projection of the internal
registry: no JSON schema, prompt hints, timeouts or auth internals leak.
Availability uses the same filter pipeline as Effective Tool Manifest.
"""
from __future__ import annotations

import hashlib
from typing import Any

from chat_sync.ai_models import ChatThreadPreferences
from chat_sync.ai_runtime.tools.public_projector import (
    P4_SERVER_TOOL_NAMES,
    PUBLIC_CATALOG_CONTRACT_REVISION,
    public_description,
    public_display_name,
)
from chat_sync.ai_runtime.tools.registry import build_server_tool_registry
from chat_sync.ai_services.effective_tool_manifest_service import (
    evaluate_public_catalog_tools,
    feature_flags_from_settings,
)


def _model_supports_tools() -> bool:
    try:
        from chat_sync.ai_runtime.providers.factory import resolve_chat_route

        return bool(resolve_chat_route().supports_tool_use)
    except Exception:
        return False


def _thread_has_sources(thread) -> bool:
    from chat_sync.ai_models import ChatTurnContextSnapshot

    snapshot = (
        ChatTurnContextSnapshot.objects.select_related("run")
        .filter(run__thread=thread, run__user_id=thread.user_id)
        .order_by("-id")
        .first()
    )
    if snapshot is None:
        return False
    return bool(snapshot.sources)


def build_thread_tool_catalog(*, thread) -> dict[str, Any]:
    prefs, _ = ChatThreadPreferences.objects.get_or_create(thread=thread)
    flags = feature_flags_from_settings()
    registry = build_server_tool_registry()
    model_supports = _model_supports_tools() if flags.agentic_tools_enabled else False
    has_sources = _thread_has_sources(thread) if flags.agentic_tools_enabled else False
    knowledge_base_ids = [str(item) for item in (prefs.knowledge_bases or []) if str(item).strip()]
    evaluated = evaluate_public_catalog_tools(
        member_id=thread.member_id,
        has_sources=has_sources,
        knowledge_base_ids=knowledge_base_ids,
        model_supports_tools=model_supports,
        thread_enabled_tools=prefs.enabled_tools or [],
        feature_flags=flags,
        registry=registry,
    )

    tools: list[dict[str, Any]] = []
    for item in evaluated:
        name = item["name"]
        tools.append(
            {
                "name": name,
                "version": item["version"],
                "display_name": public_display_name(name),
                "description": public_description(name),
                "target": item["target"],
                "risk": "read_only",
                "enabled": item["enabled"],
                "available": item["available"],
                "unavailable_reason": item["unavailable_reason"],
                "requires": item["requires"],
            }
        )

    canonical = "|".join(
        f"{item['name']}:{item['version']}:{item['available']}:{item['unavailable_reason']}"
        for item in tools
    )
    digest = hashlib.sha256(f"{PUBLIC_CATALOG_CONTRACT_REVISION}|{canonical}".encode("utf-8")).hexdigest()
    return {
        "catalog_revision": f"sha256:{digest}",
        "preferences_revision": prefs.revision,
        "tools": tools,
    }


def validate_enabled_tools(names: list[str] | tuple[str, ...] | None) -> list[str]:
    """Preferences may only persist names inside the P4 catalog allowlist."""
    cleaned: list[str] = []
    for raw in names or ():
        name = str(raw or "").strip()
        if not name:
            continue
        if name not in P4_SERVER_TOOL_NAMES:
            from common.exceptions import APIError

            raise APIError(
                "chat_tool_not_in_catalog",
                code=40092,
                status_code=400,
                details={"tool": name},
            )
        if name not in cleaned:
            cleaned.append(name)
    return cleaned


__all__ = ["build_thread_tool_catalog", "validate_enabled_tools"]
