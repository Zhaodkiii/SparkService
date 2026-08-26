from __future__ import annotations

import base64
import json
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any

from chat_sync.ai_models.knowledge import KnowledgeDocument

# 与 chat_sync/views.py 的 v2 cursor 思路一致（server_updated_at + tie-breaker id），
# 使用独立前缀避免与 Chat 消息同步的 cursor 混用/误解析。
CURSOR_PREFIX = "k1:"


def document_to_payload(document: KnowledgeDocument) -> dict[str, Any]:
    """知识文档统一 DTO：Push ACK、Pull、（后续）Web CRUD 共用同一形状，避免字段漂移。"""
    return {
        "id": str(document.id),
        "knowledge_base_id": str(document.knowledge_base_id),
        "title": document.title,
        "content": document.content,
        "excerpt": document.excerpt,
        "scope": document.scope,
        "bound_model_id": document.bound_model_id,
        "source": document.source,
        "revision": document.revision,
        "content_hash": document.content_hash,
        "is_deleted": document.is_deleted,
        "deleted_at": document.deleted_at.isoformat() if document.deleted_at else None,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "server_updated_at": document.server_updated_at.isoformat() if document.server_updated_at else None,
    }


def encode_cursor(*, server_updated_at: datetime, tie_breaker: str) -> str:
    payload = {"ts": server_updated_at.astimezone(dt_timezone.utc).isoformat(), "id": tie_breaker}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{CURSOR_PREFIX}{token}"


def decode_cursor(cursor: str | None) -> tuple[datetime | None, str | None]:
    if not cursor:
        return None, None
    if not cursor.startswith(CURSOR_PREFIX):
        return None, None
    token = cursor[len(CURSOR_PREFIX) :]
    try:
        padding = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode((token + padding).encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        ts = data.get("ts")
        tie = data.get("id")
        if not ts:
            return None, None
        dt = datetime.fromisoformat(ts)
        return dt, (str(tie) if tie is not None else None)
    except Exception:
        return None, None
