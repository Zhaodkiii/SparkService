"""Runtime 多模态图片内容组装（CHAT-WEB-029）。

按 ``run.request_snapshot`` 中的图片附件 ``file_id`` 解析 ManagedFile，从 OSS
读取真实字节并用 Pillow 重新校验，转换为 OpenAI 兼容的 ``image_url`` data
URL content part。不信任客户端提交的 URL/base64。

约束：
- 任何读取/校验失败都抛 ``ContextBuildError("chat_image_read_failed")``，
  使 Run 明确失败，不静默移除图片降级为纯文本；
- 日志只记录 file_id、mime、字节数与耗时，不记录 URL/base64/图片内容。
"""

from __future__ import annotations

import base64
import logging
import time
from io import BytesIO
from typing import Any

from PIL import Image

from chat_sync.ai_services.context.context_builder import ContextBuildError
from chat_sync.ai_services.image_support import MAX_IMAGE_BYTES, image_attachments_from, resolve_image_managed_file
from file_manager.services.oss_object_service import OssUploadError, get_bytes

logger = logging.getLogger("chat_sync.ai.image_content")

# 图片-only 消息注入的用户文本（工单 23.3）
IMAGE_ONLY_PROMPT = "请分析用户发送的图片，并在无法判断时说明需要补充的信息"

# Pillow 格式名 → MIME（与 image_support.ALLOWED_IMAGE_MIME_TYPES 对齐）
_PIL_FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}


def has_image_attachments(request_snapshot: dict[str, Any] | None) -> bool:
    """run 快照的 attachments 中是否包含 type=image 附件。"""
    return bool(image_attachments_from((request_snapshot or {}).get("attachments")))


def build_image_content_parts(*, user, run) -> list[dict[str, Any]]:
    """把 run 快照中的图片附件转换为 image_url data URL parts（按 order 排序）。"""
    parts: list[dict[str, Any]] = []
    for item in image_attachments_from((run.request_snapshot or {}).get("attachments")):
        file_id = item.get("file_id")
        start_time = time.perf_counter()
        managed = resolve_image_managed_file(user=user, file_id=file_id)
        if managed is None or not managed.object_key:
            raise ContextBuildError("chat_image_read_failed", "image attachment not accessible")
        try:
            raw = get_bytes(object_key=managed.object_key, max_bytes=MAX_IMAGE_BYTES)
        except OssUploadError as exc:
            logger.warning("chat_image.read_failed file_id=%s reason=%s", managed.id, str(exc))
            raise ContextBuildError("chat_image_read_failed", "image object read failed") from exc
        mime = _verified_image_mime(raw, managed.mime_type)
        if mime is None:
            logger.warning("chat_image.decode_failed file_id=%s", managed.id)
            raise ContextBuildError("chat_image_read_failed", "image bytes failed validation")
        encoded = base64.b64encode(raw).decode("ascii")
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        # 只记 file_id、mime、字节数、耗时；不记 URL/base64/内容。
        logger.info(
            "chat_image.part_built file_id=%s mime_type=%s bytes=%s duration_ms=%s",
            managed.id,
            mime,
            len(raw),
            duration_ms,
        )
    return parts


def build_multimodal_user_content(*, user, run, current_text: str) -> list[dict[str, Any]]:
    """文字 + 图片组装为 OpenAI content parts；无文字时注入 IMAGE_ONLY_PROMPT。"""
    text = (current_text or "").strip() or IMAGE_ONLY_PROMPT
    return [{"type": "text", "text": text}] + build_image_content_parts(user=user, run=run)


def _verified_image_mime(raw: bytes, declared_mime: str) -> str | None:
    """Pillow 校验字节可解码且真实格式与声明 MIME 一致；通过返回该 MIME。"""
    if not raw:
        return None
    try:
        with Image.open(BytesIO(raw)) as image:
            detected = image.format
            image.verify()
    except Exception:
        return None
    real_mime = _PIL_FORMAT_TO_MIME.get(detected or "")
    if real_mime is None or real_mime != declared_mime:
        return None
    return real_mime
