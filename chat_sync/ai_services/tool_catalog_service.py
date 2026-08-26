"""P4 Public Tool Catalog.

Computes, per user/thread/model/context, which read-only server tools the Web
may display and toggle. The catalog is an allowlist projection of the internal
registry: no JSON schema, prompt hints, timeouts or auth internals leak.
"""
from __future__ import annotations

import hashlib
from typing import Any

from django.conf import settings

from chat_sync.ai_models import ChatThreadPreferences
from chat_sync.ai_runtime.tools.public_projector import (
    P4_SERVER_TOOL_NAMES,
    PUBLIC_CATALOG_CONTRACT_REVISION,
    public_description,
    public_display_name,
)
from chat_sync.ai_runtime.tools.registry import build_server_tool_registry

_REASONS = {
    "feature_disabled",
    "model_unsupported",
    "member_required",
    "source_required",
}


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
    registry = build_server_tool_registry()
    feature_enabled = bool(getattr(settings, "CHAT_AI_AGENTIC_TOOLS_ENABLED", False))
    model_supports = _model_supports_tools() if feature_enabled else False
    has_member = thread.member_id is not None
    has_sources = _thread_has_sources(thread) if feature_enabled else False
    enabled_names = {str(name) for name in (prefs.enabled_tools or [])}

    tools: list[dict[str, Any]] = []
    for name in P4_SERVER_TOOL_NAMES:
        entry = registry.get(name)
        version = entry.policy.version if entry else "v1"
        required_context = list(entry.policy.required_context) if entry else []
        reason: str | None = None
        if not feature_enabled:
            reason = "feature_disabled"
        elif not model_supports:
            reason = "model_unsupported"
        elif "member" in required_context and not has_member:
            reason = "member_required"
        elif "source" in required_context and not has_sources:
            reason = "source_required"
        tools.append(
            {
                "name": name,
                "version": version,
                "display_name": public_display_name(name),
                "description": public_description(name),
                "target": "server",
                "risk": "read_only",
                "enabled": name in enabled_names,
                "available": reason is None,
                "unavailable_reason": reason,
                "requires": required_context,
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
