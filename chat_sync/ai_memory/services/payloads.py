from __future__ import annotations

import base64
import json
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any

from chat_sync.ai_models.memory import AIMemory

CURSOR_PREFIX = "m1:"


def memory_to_snapshot(memory: AIMemory) -> dict[str, Any]:
    """Shared snapshot for Push ACK, Pull, and entry CRUD."""
    return {
        "id": str(memory.id),
        "scope": memory.scope,
        "scope_key": memory.scope_key,
        "member_id": memory.member_id,
        "agent_key": memory.agent_key,
        "thread_id": str(memory.thread_id) if memory.thread_id else None,
        "layer": memory.layer,
        "document_key": memory.document_key,
        "section_key": memory.section_key,
        "memory_type": memory.memory_type,
        "normalized_key": memory.normalized_key,
        "title": memory.title,
        "content": memory.content,
        "structured_value": memory.structured_value or {},
        "is_pinned": memory.is_pinned,
        "sort_order": memory.sort_order,
        "source": memory.source,
        "confidence": float(memory.confidence) if memory.confidence is not None else None,
        "confirmation_status": memory.confirmation_status,
        "confirmed_at": memory.confirmed_at.isoformat() if memory.confirmed_at else None,
        "sensitivity": memory.sensitivity,
        "status": memory.status,
        "expires_at": memory.expires_at.isoformat() if memory.expires_at else None,
        "last_confirmed_at": memory.last_confirmed_at.isoformat() if memory.last_confirmed_at else None,
        "last_used_at": memory.last_used_at.isoformat() if memory.last_used_at else None,
        "superseded_by_id": str(memory.superseded_by_id) if memory.superseded_by_id else None,
        "content_hash": memory.content_hash,
        "dedup_key": memory.dedup_key,
        "revision": memory.revision,
        "is_deleted": memory.is_deleted,
        "deleted_at": memory.deleted_at.isoformat() if memory.deleted_at else None,
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
        "server_updated_at": memory.server_updated_at.isoformat() if memory.server_updated_at else None,
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
