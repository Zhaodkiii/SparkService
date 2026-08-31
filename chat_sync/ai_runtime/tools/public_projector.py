"""P4 public tool projection.

Every byte handed to the Web must pass through this module. Raw arguments,
result content, result metadata, error messages and internal hashes never
leave the server; only the allow-listed display projection below is public.
"""
from __future__ import annotations

from typing import Any, Iterable

# P4 exposes exactly these server-side read-only tools. ask_user, client
# tools, deferred/MCP tools stay hidden until P5/P6.
P4_SERVER_TOOL_NAMES: tuple[str, ...] = (
    "get_current_member",
    "query_member_profile",
    "list_member_health_sources",
    "get_health_resource_context",
    "read_source",
)

# revision of the public catalog contract itself; bump when display rules change.
PUBLIC_CATALOG_CONTRACT_REVISION = "p4.v1"

SECTION_LABELS: dict[str, str] = {
    "allergies": "过敏史",
    "chronic_conditions": "慢性病",
    "medication_focus": "用药关注",
}

RESOURCE_TYPE_LABELS: dict[str, str] = {
    "health_exam_report": "体检报告",
    "examination_report": "检查报告",
    "medical_case": "病例",
    "medication_plan": "用药计划",
    "member_key_indicator": "关键指标",
    "member_profile": "健康档案",
    "attachment": "附件",
}

TOOL_DISPLAY: dict[str, dict[str, str]] = {
    "ask_user": {
        "display_name": "确认信息",
        "description": "向你确认继续分析所需的信息",
    },
    "get_current_member": {
        "display_name": "查看当前成员",
        "description": "确认当前对话选择的成员",
    },
    "query_member_profile": {
        "display_name": "读取健康档案",
        "description": "在需要时读取当前成员已授权的档案分区",
    },
    "list_member_health_sources": {
        "display_name": "查找健康资料",
        "description": "查找当前成员可用的健康资料",
    },
    "get_health_resource_context": {
        "display_name": "读取健康资料",
        "description": "读取指定健康资料的安全上下文",
    },
    "read_source": {
        "display_name": "读取参考资料",
        "description": "读取本轮对话已附加的参考资料",
    },
    "read_memory": {
        "display_name": "读取记忆",
        "description": "在需要个性化回答时读取已确认的长期记忆",
    },
    "write_memory": {
        "display_name": "保存偏好",
        "description": "仅保存你明确表达的长期回答偏好",
    },
}

# error_code -> (public code, message_key, retryable)
# Permission and existence failures intentionally share one public code so the
# Web cannot distinguish "not registered" from "no access".
ERROR_PROJECTION: dict[str, tuple[str, str, bool]] = {
    "invalid_arguments": ("invalid_arguments", "tool_invalid_arguments", False),
    "arguments_too_large": ("invalid_arguments", "tool_invalid_arguments", False),
    "schema_validation_failed": ("schema_validation_failed", "tool_schema_validation_failed", False),
    "tool_arguments_schema_invalid": ("schema_validation_failed", "tool_schema_validation_failed", False),
    "tool_not_available": ("tool_not_available", "tool_not_available", False),
    "duplicate_tool_call": ("duplicate_tool_call", "tool_duplicate_call", False),
    "tool_call_limit": ("tool_call_limit", "tool_call_limit", False),
    "tool_timeout": ("timeout", "tool_timeout", True),
    "tool_execution_failed": ("tool_execution_failed", "tool_execution_failed", True),
    "tool_permission_denied": ("tool_unavailable", "tool_unavailable", False),
    "tool_resource_not_found": ("tool_unavailable", "tool_unavailable", False),
    "tool_source_missing": ("tool_unavailable", "tool_unavailable", False),
    "memory_disabled": ("tool_unavailable", "tool_unavailable", False),
    "memory_write_not_allowed": ("tool_unavailable", "tool_unavailable", False),
    "memory_invalid_preference": ("invalid_arguments", "tool_invalid_arguments", False),
    "memory_target_not_found": ("tool_unavailable", "tool_unavailable", False),
    "memory_target_conflict": ("tool_unavailable", "tool_unavailable", False),
    "memory_duplicate": ("duplicate_tool_call", "tool_duplicate_call", False),
    "memory_unavailable": ("tool_execution_failed", "tool_execution_failed", True),
}

DEFAULT_ERROR_PROJECTION: tuple[str, str, bool] = ("tool_execution_failed", "tool_execution_failed", True)

_MAX_SOURCE_REFS = 8


def public_display_name(name: str) -> str:
    entry = TOOL_DISPLAY.get(str(name or ""))
    return entry["display_name"] if entry else "服务工具"


def public_description(name: str) -> str:
    entry = TOOL_DISPLAY.get(str(name or ""))
    return entry["description"] if entry else "服务端只读工具"


def is_p4_server_tool(name: str) -> bool:
    return str(name or "") in P4_SERVER_TOOL_NAMES


def _label_sections(values: Iterable[Any]) -> list[str]:
    labels: list[str] = []
    for value in values or ():
        key = str(value or "")
        labels.append(SECTION_LABELS.get(key, key))
    return labels[:8]


def _label_resource_type(value: Any) -> str:
    key = str(value or "")
    if ":" in key:  # e.g. "health_exam_report:42" -> display name only
        key = key.split(":", 1)[0]
    return RESOURCE_TYPE_LABELS.get(key, "健康资料")


def public_args(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Allow-listed, translated argument projection. Unknown keys are dropped."""
    args = arguments if isinstance(arguments, dict) else {}
    tool = str(name or "")
    if tool == "query_member_profile":
        sections = args.get("sections")
        if isinstance(sections, list) and sections:
            return {"sections": _label_sections(sections)}
        return {}
    if tool == "list_member_health_sources":
        projected: dict[str, Any] = {}
        types = args.get("resource_types")
        if isinstance(types, list) and types:
            projected["resource_types"] = [_label_resource_type(item) for item in types[:8]]
        limit = args.get("limit")
        if isinstance(limit, int) and not isinstance(limit, bool):
            projected["limit"] = limit
        return projected
    if tool == "get_health_resource_context":
        resource_type = args.get("resource_type")
        if resource_type is not None:
            return {"resource_type": _label_resource_type(resource_type)}
        return {}
    if tool == "read_source":
        source_id = args.get("source_id")
        if isinstance(source_id, str) and source_id:
            return {"source_id": _label_resource_type(source_id)}
        return {}
    return {}


def public_result_preview(
    name: str,
    *,
    success: bool,
    arguments: dict[str, Any] | None,
    source_refs: Iterable[dict[str, Any]] | None = None,
    duplicate: bool = False,
) -> str | None:
    """Server-generated short summary for UI only; never the model observation."""
    if duplicate:
        return "已复用相同请求的结果"
    if not success:
        return None
    tool = str(name or "")
    args = arguments if isinstance(arguments, dict) else {}
    if tool == "get_current_member":
        return "已确认当前成员"
    if tool == "query_member_profile":
        sections = args.get("sections")
        count = len(sections) if isinstance(sections, list) and sections else 3
        return f"已读取 {count} 个健康档案分区"
    if tool == "list_member_health_sources":
        count = len(list(source_refs or ()))
        return f"找到 {count} 项可用资料"
    if tool == "get_health_resource_context":
        return "已读取健康资料"
    if tool == "read_source":
        return "已读取参考资料"
    if tool == "ask_user":
        return "已收到你的确认"
    if tool == "read_memory":
        count = len(list(source_refs or ()))
        if count:
            return f"已读取 {count} 条记忆"
        return "没有可读取的长期记忆"
    if tool == "write_memory":
        return "已保存回答偏好"
    return "已完成"


def public_error(error_code: str | None) -> dict[str, Any] | None:
    code = str(error_code or "")
    if not code:
        return None
    public_code, message_key, retryable = ERROR_PROJECTION.get(code, DEFAULT_ERROR_PROJECTION)
    return {"code": public_code, "message_key": message_key, "retryable": retryable}


def safe_source_refs(sources: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Keep only source_id/type/title; never trust tool-returned URLs or extras."""
    projected: list[dict[str, Any]] = []
    for raw in list(sources or ())[:_MAX_SOURCE_REFS]:
        if not isinstance(raw, dict):
            continue
        item: dict[str, Any] = {
            "source_id": str(raw.get("source_id") or "")[:255],
            "type": str(raw.get("type") or "unknown")[:64],
        }
        title = raw.get("title")
        if isinstance(title, str) and title:
            item["title"] = title[:255]
        if item["source_id"]:
            projected.append(item)
    return projected


__all__ = [
    "P4_SERVER_TOOL_NAMES",
    "PUBLIC_CATALOG_CONTRACT_REVISION",
    "is_p4_server_tool",
    "public_args",
    "public_description",
    "public_display_name",
    "public_error",
    "public_result_preview",
    "safe_source_refs",
]
