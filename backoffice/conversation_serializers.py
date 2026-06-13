from __future__ import annotations

import json
from typing import Any

from django.contrib.auth import get_user_model
from django.utils import timezone

from chat_sync.models import ChatMessage, ChatMessageBlock, ChatThread
from chat_sync.views import _block_to_payload

User = get_user_model()

PAYLOAD_INLINE_BYTE_LIMIT = 4096

HEAVY_BLOCK_KINDS: set[str] = {
    "healthCards",
    "structuredHealthCards",
    "nutritionCards",
    "healthResourceReference",
    "sleepVisualization",
    "workoutVisualization",
    "knowledgeCards",
    "mapRoute",
    "events",
    "pendingMemberToolCards",
    "captureCard",
    "taskCards",
}

MEDICAL_BLOCK_KINDS: set[str] = HEAVY_BLOCK_KINDS | {
    "medicalRiskNotice",
    "medicalDisclaimerCard",
    "tool",
    "imageGallery",
    "fileAttachments",
}

_KIND_SNAKE_ALIASES = {v: k for k, v in {
    "deep_thought": "deepThought",
    "translated_text": "translatedText",
    "image_gallery": "imageGallery",
    "file_attachments": "fileAttachments",
    "knowledge_cards": "knowledgeCards",
    "map_route": "mapRoute",
    "health_cards": "healthCards",
    "pending_member_tool_cards": "pendingMemberToolCards",
    "structured_health_cards": "structuredHealthCards",
    "sleep_visualization": "sleepVisualization",
    "nutrition_cards": "nutritionCards",
    "workout_visualization": "workoutVisualization",
    "capture_card": "captureCard",
    "small_task_card": "smallTaskCard",
    "task_cards": "taskCards",
    "assistant_status_card": "assistantStatusCard",
    "health_resource_reference": "healthResourceReference",
    "medical_risk_notice": "medicalRiskNotice",
    "medical_disclaimer_card": "medicalDisclaimerCard",
}.items()}


def block_kind_filter_values(kinds: set[str]) -> list[str]:
    values = set(kinds)
    for kind in kinds:
        snake = _KIND_SNAKE_ALIASES.get(kind)
        if snake:
            values.add(snake)
        camel = _normalize_block_kind(kind)
        values.add(camel)
    return sorted(values)

INLINE_BLOCK_KINDS: set[str] = {
    "text",
    "translatedText",
    "deepThought",
    "error",
    "assistantStatusCard",
    "medicalRiskNotice",
    "medicalDisclaimerCard",
    "html",
    "smallTaskCard",
}

BLOCK_KIND_LABELS: dict[str, str] = {
    "text": "文本",
    "deepThought": "AI 思考过程",
    "tool": "工具调用",
    "imageGallery": "图片",
    "fileAttachments": "文件附件",
    "knowledgeCards": "知识卡片",
    "translatedText": "翻译文本",
    "mapRoute": "地图路线",
    "events": "日程事件",
    "healthCards": "健康卡片",
    "pendingMemberToolCards": "待选成员",
    "structuredHealthCards": "结构化健康数据",
    "sleepVisualization": "睡眠可视化",
    "nutritionCards": "营养卡片",
    "workoutVisualization": "运动可视化",
    "captureCard": "采集卡片",
    "html": "HTML",
    "smallTaskCard": "小任务",
    "taskCards": "任务卡片",
    "error": "错误",
    "assistantStatusCard": "助手状态",
    "healthResourceReference": "健康资料引用",
    "medicalRiskNotice": "医疗风险提示",
    "medicalDisclaimerCard": "医疗免责声明",
}


def is_anonymized_user(user) -> bool:
    username = (user.username or "").strip()
    email = (user.email or "").strip()
    return username.startswith("deleted_user_") or email.endswith("@anonymized.local")


def format_user_display_name(user) -> str:
    if is_anonymized_user(user):
        return f"匿名用户 #{user.id}"
    return user.username


def format_user_status(user) -> str:
    if is_anonymized_user(user):
        return "注销"
    if user.is_active:
        return "启用"
    return "禁用"


def _truncate(text: str, limit: int = 120) -> str:
    trimmed = (text or "").strip()
    if len(trimmed) <= limit:
        return trimmed
    return trimmed[:limit] + "…"


def _normalize_block_kind(raw_kind: str) -> str:
    aliases = {
        "deep_thought": "deepThought",
        "translated_text": "translatedText",
        "image_gallery": "imageGallery",
        "file_attachments": "fileAttachments",
        "knowledge_cards": "knowledgeCards",
        "map_route": "mapRoute",
        "health_cards": "healthCards",
        "pending_member_tool_cards": "pendingMemberToolCards",
        "structured_health_cards": "structuredHealthCards",
        "sleep_visualization": "sleepVisualization",
        "nutrition_cards": "nutritionCards",
        "workout_visualization": "workoutVisualization",
        "capture_card": "captureCard",
        "small_task_card": "smallTaskCard",
        "task_cards": "taskCards",
        "assistant_status_card": "assistantStatusCard",
        "health_resource_reference": "healthResourceReference",
        "medical_risk_notice": "medicalRiskNotice",
        "medical_disclaimer_card": "medicalDisclaimerCard",
    }
    if raw_kind in aliases:
        return aliases[raw_kind]
    return raw_kind


def _unwrap_swift_enum(value):
    if isinstance(value, dict) and "_0" in value:
        return value.get("_0")
    return value


def _resolve_block_presentation(kind: str, payload: dict) -> tuple[str, dict]:
    payload = payload or {}
    nested = payload.get("payload")
    if isinstance(nested, dict) and len(nested) == 1:
        raw_kind, raw_value = next(iter(nested.items()))
        resolved_kind = _normalize_block_kind(str(raw_kind))
        unwrapped = _unwrap_swift_enum(raw_value)
        if resolved_kind in {"text", "translatedText", "html", "error"}:
            text = unwrapped if isinstance(unwrapped, str) else _payload_text(unwrapped or {})
            return resolved_kind, {**payload, "text": text}
        if resolved_kind == "deepThought" and isinstance(unwrapped, dict):
            return resolved_kind, {
                **payload,
                "reasoningContent": unwrapped.get("reasoningContent") or unwrapped.get("reasoning_content"),
                "reasoningDurationMs": unwrapped.get("reasoningDurationMs") or unwrapped.get("reasoning_duration_ms"),
            }
        if resolved_kind == "tool" and isinstance(unwrapped, dict):
            return resolved_kind, {**payload, **unwrapped}
        if resolved_kind in {"imageGallery", "fileAttachments"}:
            attachments = unwrapped if isinstance(unwrapped, list) else payload.get("attachments") or []
            return resolved_kind, {**payload, "attachments": attachments}
        if isinstance(unwrapped, list):
            return resolved_kind, {**payload, "cards": unwrapped}
        if isinstance(unwrapped, dict):
            return resolved_kind, {**payload, **unwrapped}
        if isinstance(unwrapped, str):
            return resolved_kind, {**payload, "text": unwrapped}
        return resolved_kind, payload
    return _normalize_block_kind(kind or str(payload.get("kind") or "unknown")), payload


def _payload_byte_size(payload: Any) -> int:
    try:
        return len(json.dumps(payload, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return 0


def is_heavy_block(resolved_kind: str, payload: dict) -> bool:
    if resolved_kind in HEAVY_BLOCK_KINDS:
        return True
    if resolved_kind in INLINE_BLOCK_KINDS:
        if resolved_kind in {"medicalRiskNotice", "medicalDisclaimerCard"}:
            return _payload_byte_size(payload) > PAYLOAD_INLINE_BYTE_LIMIT
        return False
    if resolved_kind in {"tool", "imageGallery", "fileAttachments", "knowledgeCards"}:
        return _payload_byte_size(payload) > PAYLOAD_INLINE_BYTE_LIMIT
    return _payload_byte_size(payload) > PAYLOAD_INLINE_BYTE_LIMIT


def block_detail_endpoint(user_id: int, thread_id, block_id) -> str:
    return f"/api/admin/v1/conversations/users/{user_id}/threads/{thread_id}/blocks/{block_id}/detail/"


def message_debug_endpoint(user_id: int, thread_id, message_db_id: int) -> str:
    return (
        f"/api/admin/v1/conversations/users/{user_id}/threads/{thread_id}/messages/{message_db_id}/debug/"
    )


def _read_cards_from_payload(payload: dict) -> list[dict]:
    candidates = [
        payload.get("cards"),
        payload.get("items"),
        payload.get("healthCards"),
        payload.get("structuredCards"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    blob = payload.get("blob")
    if isinstance(blob, dict) and isinstance(blob.get("cards"), list):
        return [item for item in blob["cards"] if isinstance(item, dict)]
    return []


def _pick_card_title(card: dict, fallback: str = "卡片") -> str:
    for key in ("title", "mealName", "meal_name", "name", "displayTitle", "display_title", "label"):
        value = card.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _pick_scalar(payload: dict, keys: tuple[str, ...]):
    for key in keys:
        value = payload.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, (str, int, float, bool)):
            return value
    return None


def _payload_text(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("text", "message", "content", "html"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    _, resolved = _resolve_block_presentation(payload.get("kind") or "text", payload)
    for key in ("text", "message", "content", "html"):
        value = resolved.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def summarize_block_payload(kind: str, payload: dict) -> str:
    resolved_kind, resolved_payload = _resolve_block_presentation(kind, payload or {})
    kind = resolved_kind
    payload = resolved_payload
    if kind == "text":
        return _truncate(_payload_text(payload))
    if kind == "deepThought":
        card = payload.get("reasoningContent") or payload.get("reasoning_content") or ""
        if isinstance(card, str) and card.strip():
            return _truncate(card)
        return "AI 思考过程"
    if kind == "tool":
        name = payload.get("name") or payload.get("toolName") or payload.get("tool_name") or "未知工具"
        content = payload.get("content") or payload.get("result") or payload.get("output") or payload.get("response")
        if isinstance(content, str) and content.strip():
            return f"工具调用：{name} · {_truncate(content, 80)}"
        return f"工具调用：{name}"
    if kind == "imageGallery":
        attachments = payload.get("attachments") or payload.get("images") or []
        count = len(attachments) if isinstance(attachments, list) else 0
        return f"图片 {count} 张"
    if kind == "fileAttachments":
        attachments = payload.get("attachments") or []
        count = len(attachments) if isinstance(attachments, list) else 0
        return f"文件 {count} 个"
    if kind == "translatedText":
        return _truncate(_payload_text(payload))
    if kind == "error":
        return _truncate(_payload_text(payload) or "错误")
    if kind == "html":
        return "HTML 内容"
    if kind == "nutritionCards":
        cards = _read_cards_from_payload(payload)
        if not cards:
            return "营养卡片"
        first = cards[0]
        title = _pick_card_title(first, "营养记录")
        calories = _pick_scalar(first, ("caloriesKcal", "calories_kcal"))
        protein = _pick_scalar(first, ("proteinGrams", "protein_grams"))
        parts = [title]
        if calories is not None:
            parts.append(f"热量 {calories}kcal")
        if protein is not None:
            parts.append(f"蛋白质 {protein}g")
        if len(cards) > 1:
            parts.append(f"共 {len(cards)} 条")
        return " · ".join(str(part) for part in parts)
    if kind in {"healthCards", "structuredHealthCards"}:
        cards = _read_cards_from_payload(payload)
        if not cards:
            return BLOCK_KIND_LABELS.get(kind, "健康数据")
        title = _pick_card_title(cards[0], BLOCK_KIND_LABELS.get(kind, "健康数据"))
        metric = _pick_scalar(cards[0], ("value", "metricValue", "metric_value", "latestValue", "latest_value"))
        suffix = f" · {metric}" if metric is not None else ""
        extra = f" · 共 {len(cards)} 条" if len(cards) > 1 else ""
        return f"{title}{suffix}{extra}"
    if kind == "sleepVisualization":
        duration = _pick_scalar(payload, ("totalDuration", "total_duration", "sleepDuration", "sleep_duration"))
        score = _pick_scalar(payload, ("sleepScore", "sleep_score", "score"))
        parts = ["睡眠数据"]
        if duration is not None:
            parts.append(f"时长 {duration}")
        if score is not None:
            parts.append(f"评分 {score}")
        return " · ".join(str(part) for part in parts)
    if kind == "workoutVisualization":
        workout_type = _pick_scalar(payload, ("workoutType", "workout_type", "activityType", "activity_type", "type"))
        duration = _pick_scalar(payload, ("duration", "durationMinutes", "duration_minutes"))
        calories = _pick_scalar(payload, ("calories", "caloriesKcal", "calories_kcal"))
        parts = [str(workout_type or "运动数据")]
        if duration is not None:
            parts.append(f"时长 {duration}")
        if calories is not None:
            parts.append(f"消耗 {calories}")
        return " · ".join(str(part) for part in parts)
    if kind == "healthResourceReference":
        title = _pick_scalar(payload, ("title", "resourceTitle", "resource_title", "name", "summary"))
        return str(title or "健康资料引用")
    if kind == "knowledgeCards":
        cards = _read_cards_from_payload(payload)
        if not cards:
            return "知识卡片"
        title = _pick_card_title(cards[0], "知识卡片")
        return f"{title} · 共 {len(cards)} 条" if len(cards) > 1 else title
    if kind == "medicalRiskNotice":
        title = _pick_scalar(payload, ("displayTitle", "display_title", "title"))
        return str(title or "医疗风险提示")
    if kind == "medicalDisclaimerCard":
        title = _pick_scalar(payload, ("displayTitle", "display_title", "title"))
        return str(title or "医疗免责声明")
    label = BLOCK_KIND_LABELS.get(kind)
    if label:
        cards = _read_cards_from_payload(payload)
        if cards:
            return f"{label} · 共 {len(cards)} 条"
        return label
    return f"未知内容：{kind}"


def block_sort_key(block: ChatMessageBlock) -> tuple:
    if block.order_key is not None:
        return (0, block.order_key, block.created_at, str(block.id))
    return (1, 0, block.created_at, str(block.id))


def ordered_blocks(message: ChatMessage) -> list[ChatMessageBlock]:
    return sorted(message.blocks.all(), key=block_sort_key)


def _block_detail_fields(
    *,
    user_id: int | None,
    thread_id,
    block_id,
    resolved_kind: str,
    payload: dict,
    detail_mode: str,
) -> dict[str, Any]:
    heavy = is_heavy_block(resolved_kind, payload)
    endpoint = block_detail_endpoint(user_id, thread_id, block_id) if user_id and thread_id else None
    if detail_mode == "detail":
        return {
            "payload": payload,
            "has_heavy_detail": heavy,
            "detail_load_mode": "lazy" if heavy else "inline",
            "detail_endpoint": endpoint if heavy else None,
            "detail_status": "loaded",
        }
    if heavy:
        return {
            "payload": None,
            "has_heavy_detail": True,
            "detail_load_mode": "lazy",
            "detail_endpoint": endpoint,
            "detail_status": "not_loaded",
        }
    return {
        "payload": payload,
        "has_heavy_detail": False,
        "detail_load_mode": "inline",
        "detail_endpoint": None,
        "detail_status": "loaded",
    }


def serialize_block(
    block: ChatMessageBlock,
    *,
    user_id: int | None = None,
    thread_id=None,
    detail_mode: str = "list",
) -> dict[str, Any]:
    payload = _block_to_payload(block)
    kind = block.kind or payload.get("kind") or "unknown"
    resolved_kind, resolved_payload = _resolve_block_presentation(kind, payload)
    detail_fields = _block_detail_fields(
        user_id=user_id,
        thread_id=thread_id,
        block_id=block.id,
        resolved_kind=resolved_kind,
        payload=payload,
        detail_mode=detail_mode,
    )
    return {
        "id": str(block.id),
        "kind": kind,
        "resolved_kind": resolved_kind,
        "status": block.status,
        "revision": block.revision,
        "order_key": block.order_key,
        "tool_call_id": block.tool_call_id or None,
        "parent_tool_call_id": block.parent_tool_call_id or None,
        "parent_block_id": str(block.parent_block_id) if block.parent_block_id else None,
        "node_role": block.node_role,
        "anchor": block.anchor,
        "block_summary": summarize_block_payload(kind, payload),
        "created_at": block.created_at.isoformat() if block.created_at else None,
        "updated_at": block.updated_at.isoformat() if block.updated_at else None,
        **detail_fields,
    }


def _legacy_virtual_blocks(
    message: ChatMessage,
    *,
    user_id: int | None = None,
    thread_id=None,
    detail_mode: str = "list",
) -> list[dict[str, Any]]:
    metadata = message.metadata or {}
    virtual: list[dict[str, Any]] = []
    resolved_user_id = user_id or message.user_id
    resolved_thread_id = thread_id or message.thread_id

    reasoning = metadata.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        payload = {
            "reasoningContent": reasoning,
            "reasoningDurationMs": metadata.get("reasoning_duration_ms"),
        }
        virtual.append(
            {
                "id": f"legacy-reasoning-{message.id}",
                "kind": "deepThought",
                "resolved_kind": "deepThought",
                "status": "ready",
                "revision": 0,
                "order_key": None,
                "tool_call_id": None,
                "parent_tool_call_id": None,
                "parent_block_id": None,
                "node_role": "timeline",
                "anchor": None,
                "block_summary": "AI 思考过程",
                "created_at": message.created_at.isoformat() if message.created_at else None,
                "updated_at": message.server_updated_at.isoformat() if message.server_updated_at else None,
                "is_virtual": True,
                **_block_detail_fields(
                    user_id=resolved_user_id,
                    thread_id=resolved_thread_id,
                    block_id=f"legacy-reasoning-{message.id}",
                    resolved_kind="deepThought",
                    payload=payload,
                    detail_mode=detail_mode,
                ),
            }
        )

    attachments = metadata.get("attachments") or []
    if isinstance(attachments, list) and attachments:
        payload = {"attachments": attachments, "source": "metadata.attachments"}
        virtual.append(
            {
                "id": f"legacy-attachments-{message.id}",
                "kind": "fileAttachments",
                "resolved_kind": "fileAttachments",
                "status": "ready",
                "revision": 0,
                "order_key": None,
                "tool_call_id": None,
                "parent_tool_call_id": None,
                "parent_block_id": None,
                "node_role": "timeline",
                "anchor": None,
                "block_summary": f"历史附件 {len(attachments)} 个",
                "created_at": message.created_at.isoformat() if message.created_at else None,
                "updated_at": message.server_updated_at.isoformat() if message.server_updated_at else None,
                "is_virtual": True,
                **_block_detail_fields(
                    user_id=resolved_user_id,
                    thread_id=resolved_thread_id,
                    block_id=f"legacy-attachments-{message.id}",
                    resolved_kind="fileAttachments",
                    payload=payload,
                    detail_mode=detail_mode,
                ),
            }
        )

    return virtual


def serialize_message(
    message: ChatMessage,
    *,
    include_raw: bool = False,
    detail_mode: str = "list",
) -> dict[str, Any]:
    blocks = [
        serialize_block(
            block,
            user_id=message.user_id,
            thread_id=message.thread_id,
            detail_mode=detail_mode,
        )
        for block in ordered_blocks(message)
    ]
    if not blocks:
        blocks = _legacy_virtual_blocks(message, user_id=message.user_id, thread_id=message.thread_id)

    block_kinds = sorted({block["kind"] for block in blocks})
    preview = ""
    for block in blocks:
        summary = block.get("block_summary") or ""
        if summary:
            preview = summary
            break

    metadata = message.metadata or {}
    payload: dict[str, Any] = {
        "message_db_id": message.id,
        "thread_id": str(message.thread_id),
        "role": message.role,
        "model_name": message.model_name or None,
        "client_message_id": str(message.client_message_id),
        "server_message_id": message.server_message_id or None,
        "delivery_state": message.delivery_state,
        "tombstone": message.tombstone,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "server_updated_at": message.server_updated_at.isoformat() if message.server_updated_at else None,
        "blocks": blocks,
        "blocks_count": len(blocks),
        "block_kinds": block_kinds,
        "message_preview": preview,
        "metadata": metadata,
        "debug_endpoint": message_debug_endpoint(message.user_id, message.thread_id, message.id),
    }
    if include_raw:
        payload["raw"] = serialize_message_debug(message)
    return payload


def serialize_message_debug(message: ChatMessage) -> dict[str, Any]:
    blocks = [serialize_block(block, detail_mode="detail") for block in ordered_blocks(message)]
    if not blocks:
        blocks = _legacy_virtual_blocks(message, detail_mode="detail")
    metadata = message.metadata or {}
    return {
        "message_db_id": message.id,
        "thread_id": str(message.thread_id),
        "role": message.role,
        "model_name": message.model_name,
        "client_message_id": str(message.client_message_id),
        "server_message_id": message.server_message_id,
        "delivery_state": message.delivery_state,
        "tombstone": message.tombstone,
        "metadata": metadata,
        "blocks": blocks,
    }


def serialize_thread(thread: ChatThread, *, annotations: dict[str, Any] | None = None) -> dict[str, Any]:
    data = annotations or {}
    title = (thread.title or "").strip() or "未命名会话"
    return {
        "thread_id": str(thread.id),
        "title": title,
        "scenario": thread.scenario,
        "current_model_name": thread.current_model_name or None,
        "patient_id": str(thread.patient_id) if thread.patient_id else None,
        "member_id": thread.member_id,
        "temperature": thread.temperature,
        "top_p": thread.top_p,
        "max_tokens": thread.max_tokens,
        "max_messages": thread.max_messages,
        "role_prompt": thread.role_prompt or "",
        "image_delivery_mode": thread.image_delivery_mode,
        "is_pinned": thread.is_pinned,
        "is_deleted": thread.is_deleted,
        "deleted_at": thread.deleted_at.isoformat() if thread.deleted_at else None,
        "created_at": thread.created_at.isoformat() if thread.created_at else None,
        "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
        "server_updated_at": thread.server_updated_at.isoformat() if thread.server_updated_at else None,
        "message_count": data.get("message_count", 0),
        "tombstone_count": data.get("tombstone_count", 0),
        "user_message_count": data.get("user_message_count", 0),
        "assistant_message_count": data.get("assistant_message_count", 0),
        "last_message_at": data.get("last_message_at"),
        "has_tool": data.get("has_tool", False),
        "has_attachment": data.get("has_attachment", False),
        "has_failed_message": data.get("has_failed_message", False),
        "block_kinds": data.get("block_kinds") or [],
        "message_preview": data.get("message_preview") or "",
        "medical_block_count": data.get("medical_block_count", 0),
        "heavy_block_count": data.get("heavy_block_count", 0),
        "attachment_count": data.get("attachment_count", 0),
        "last_medical_resource_at": data.get("last_medical_resource_at"),
    }


def serialize_conversation_user(user, *, annotations: dict[str, Any]) -> dict[str, Any]:
    last_thread_id = annotations.get("last_thread_id")
    return {
        "user_id": user.id,
        "username": format_user_display_name(user),
        "raw_username": user.username,
        "email": user.email or "",
        "is_active": user.is_active,
        "user_status": format_user_status(user),
        "is_anonymized": is_anonymized_user(user),
        "thread_count": annotations.get("thread_count", 0),
        "active_thread_count": annotations.get("active_thread_count", 0),
        "deleted_thread_count": annotations.get("deleted_thread_count", 0),
        "message_count": annotations.get("message_count", 0),
        "tombstone_count": annotations.get("tombstone_count", 0),
        "user_message_count": annotations.get("user_message_count", 0),
        "assistant_message_count": annotations.get("assistant_message_count", 0),
        "last_conversation_at": annotations.get("last_conversation_at"),
        "last_thread_id": str(last_thread_id) if last_thread_id else None,
        "last_thread_title": annotations.get("last_thread_title") or "",
        "last_model_name": annotations.get("last_model_name") or "",
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
    }


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def recent_days_trend(user_id: int, days: int = 7) -> list[dict[str, Any]]:
    from django.db.models import Count
    from django.db.models.functions import TruncDate

    today = timezone.localdate()
    start = today - timezone.timedelta(days=days - 1)
    rows = (
        ChatMessage.objects.filter(user_id=user_id, created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(message_count=Count("id"))
    )
    counts = {row["day"].isoformat(): row["message_count"] for row in rows if row["day"]}
    trend = []
    for offset in range(days):
        day = start + timezone.timedelta(days=offset)
        key = day.isoformat()
        trend.append({"date": key, "message_count": counts.get(key, 0)})
    return trend
