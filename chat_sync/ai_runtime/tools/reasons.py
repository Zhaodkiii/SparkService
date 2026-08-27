"""Stable tool-filter reason codes for CHAT-AI-030."""

from __future__ import annotations


class ToolFilterReason:
    NOT_REGISTERED = "not_registered"
    EXECUTOR_MISSING = "executor_missing"
    CLIENT_ONLY = "client_only"
    MODEL_UNSUPPORTED = "model_unsupported"
    USER_DISABLED = "user_disabled"
    PERMISSION_DENIED = "permission_denied"
    CONTEXT_MISSING = "context_missing"
    FEATURE_DISABLED = "feature_disabled"
    POLICY_DENIED = "policy_denied"
    INVALID_SCHEMA = "invalid_schema"


ALL_TOOL_FILTER_REASONS: frozenset[str] = frozenset(
    (
        ToolFilterReason.NOT_REGISTERED,
        ToolFilterReason.EXECUTOR_MISSING,
        ToolFilterReason.CLIENT_ONLY,
        ToolFilterReason.MODEL_UNSUPPORTED,
        ToolFilterReason.USER_DISABLED,
        ToolFilterReason.PERMISSION_DENIED,
        ToolFilterReason.CONTEXT_MISSING,
        ToolFilterReason.FEATURE_DISABLED,
        ToolFilterReason.POLICY_DENIED,
        ToolFilterReason.INVALID_SCHEMA,
    )
)

COMPOSITION_REASON_MAP: dict[str, str] = {
    "not_registered": ToolFilterReason.NOT_REGISTERED,
    "executor_missing": ToolFilterReason.EXECUTOR_MISSING,
    "client_tools_disabled": ToolFilterReason.CLIENT_ONLY,
    "platform_unsupported": ToolFilterReason.CLIENT_ONLY,
    "client_capability_missing": ToolFilterReason.CLIENT_ONLY,
    "model_unsupported": ToolFilterReason.MODEL_UNSUPPORTED,
    "user_disabled": ToolFilterReason.USER_DISABLED,
    "permission_denied": ToolFilterReason.PERMISSION_DENIED,
    "member_required": ToolFilterReason.CONTEXT_MISSING,
    "source_required": ToolFilterReason.CONTEXT_MISSING,
    "knowledge_base_required": ToolFilterReason.CONTEXT_MISSING,
    "feature_disabled": ToolFilterReason.FEATURE_DISABLED,
    "policy_denied": ToolFilterReason.POLICY_DENIED,
    "invalid_schema": ToolFilterReason.INVALID_SCHEMA,
}


def map_composition_reason(reason: str) -> str:
    raw = str(reason or "").strip()
    return COMPOSITION_REASON_MAP.get(raw, raw or ToolFilterReason.POLICY_DENIED)


__all__ = [
    "ALL_TOOL_FILTER_REASONS",
    "COMPOSITION_REASON_MAP",
    "ToolFilterReason",
    "map_composition_reason",
]
