"""CreateRun 图片附件校验（CHAT-WEB-029）。

只在 attachments 中存在 ``type == "image"`` 的项时启用；iOS 现有不带
``type`` 字段的 attachments 请求行为完全不变。

错误码沿用 ``APIError(msg, code, status_code)`` 模式：
- chat_image_capability_unavailable = 40098（当前模型不支持图片理解）
- chat_image_count_exceeded        = 40099（单条消息超过 3 张）
- chat_image_format_invalid        = 40100（非允许的图片格式/大小）
- chat_image_not_found             = 40492（文件不存在或无权访问）
- 图片 block 与 attachments 数量不一致复用 chat_run_request_invalid = 40091
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from common.exceptions import APIError

logger = logging.getLogger("chat_sync.ai.image_support")

ALLOWED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
MAX_IMAGE_COUNT = 3
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def image_attachments_from(attachments: Any) -> list[dict[str, Any]]:
    """过滤出图片附件并按 order 排序（缺失/非法 order 按原顺序兜底）。"""
    items = [
        item
        for item in (attachments or [])
        if isinstance(item, dict) and item.get("type") == "image"
    ]

    def _order(item: dict[str, Any]) -> tuple[int, float]:
        try:
            return (0, float(item.get("order")))
        except (TypeError, ValueError):
            return (1, 0.0)

    return sorted(items, key=_order)


def resolve_image_managed_file(*, user, file_id: Any):
    """按 reference_resolver 同款规则解析 ManagedFile；不存在或无权返回 None。

    file_id 为数字时按主键查询，否则按 file_uuid 查询；统一要求
    ``is_deleted=False`` 且通过 user_can_access_file 鉴权。
    """
    from file_manager.business_access import user_can_access_file
    from file_manager.models import ManagedFile

    if file_id in (None, ""):
        return None
    query = ManagedFile.objects.prefetch_related("business_relations").filter(is_deleted=False)
    if str(file_id).isdigit():
        query = query.filter(id=int(file_id))
    else:
        try:
            file_uuid = uuid.UUID(str(file_id))
        except (TypeError, ValueError, AttributeError):
            return None
        query = query.filter(file_uuid=file_uuid)
    obj = query.first()
    if obj is None or not user_can_access_file(user, obj):
        return None
    return obj


def count_gallery_images(input_message: dict[str, Any]) -> int:
    """统计 input_message.blocks 中 imageGallery block 的图片数量。

    兼容两种 payload 形状：
    - canonical tagged union：``{"image_gallery": {"_0": {...}}]}``（`_0` 可为
      ``{"images": [...]}`` 或直接是图片列表）；
    - 工单 20.3 建议的扁平形状：``{"images": [...]}``（此时以 block.kind 判定）。
    """
    count = 0
    for block in (input_message.get("blocks") or []):
        if not isinstance(block, dict):
            continue
        payload = block.get("payload")
        if not isinstance(payload, dict):
            continue
        value: Any = None
        wrapper = payload.get("image_gallery")
        if isinstance(wrapper, dict) and "_0" in wrapper:
            value = wrapper["_0"]
        elif str(block.get("kind") or "") == "imageGallery":
            value = payload
        else:
            continue
        if isinstance(value, list):
            count += len(value)
        elif isinstance(value, dict):
            images = value.get("images")
            if not isinstance(images, list):
                images = value.get("items")
            if isinstance(images, list):
                count += len(images)
    return count


def validate_image_attachments(*, user, thread, payload: dict[str, Any]) -> None:
    """CreateRun 入口的图片附件校验；无图片附件时直接返回（保持旧行为）。"""
    image_attachments = image_attachments_from(payload.get("attachments"))
    if not image_attachments:
        return

    from chat_sync.ai_runtime.providers.factory import resolve_chat_route

    try:
        route = resolve_chat_route()
    except Exception as exc:  # 无绑定/凭证缺失等配置问题一律视为能力不可用
        logger.warning("chat_image.route_resolve_failed: %s", type(exc).__name__)
        route = None
    if route is None or not getattr(route, "supports_multimodal", False):
        raise APIError("chat_image_capability_unavailable", code=40098, status_code=400)

    if len(image_attachments) > MAX_IMAGE_COUNT:
        raise APIError(
            "chat_image_count_exceeded",
            code=40099,
            status_code=400,
            details={"count": len(image_attachments), "max": MAX_IMAGE_COUNT},
        )

    for item in image_attachments:
        file_id = item.get("file_id")
        if file_id in (None, ""):
            raise APIError("chat_image_format_invalid", code=40100, status_code=400, details={"field": "file_id"})
        managed = resolve_image_managed_file(user=user, file_id=file_id)
        if managed is None:
            raise APIError("chat_image_not_found", code=40492, status_code=404)
        if (managed.mime_type or "") not in ALLOWED_IMAGE_MIME_TYPES:
            raise APIError("chat_image_format_invalid", code=40100, status_code=400, details={"field": "mime_type"})
        if int(managed.file_size or 0) > MAX_IMAGE_BYTES:
            raise APIError("chat_image_format_invalid", code=40100, status_code=400, details={"field": "file_size"})

    gallery_count = count_gallery_images(payload.get("input_message") or {})
    if gallery_count != len(image_attachments):
        raise APIError(
            "chat_run_request_invalid",
            code=40091,
            status_code=400,
            details={"field": "input_message.blocks", "gallery_images": gallery_count, "attachments": len(image_attachments)},
        )
