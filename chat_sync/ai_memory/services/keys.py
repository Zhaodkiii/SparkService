from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from django.utils import timezone

from chat_sync.ai_memory.constants import (
    ALLOWED_SECTION_KEYS,
    L2_DOCUMENT_KEYS,
    L3_DOCUMENT_KEYS,
    MAX_CONTENT_CHARS,
    MAX_TITLE_LENGTH,
    PREFERENCE_SECTION_KEYS,
)
from chat_sync.ai_models.memory import AIMemory, MemoryLayer, MemoryScope


def normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def compute_scope_key(*, scope: str, member_id: int | None = None, agent_key: str | None = None, thread_id=None) -> str:
    if scope == MemoryScope.ACCOUNT:
        return "account"
    if scope == MemoryScope.MEMBER and member_id is not None:
        return f"member:{int(member_id)}"
    if scope == MemoryScope.AGENT and agent_key:
        return f"agent:{agent_key}"
    if scope == MemoryScope.THREAD and thread_id:
        return f"thread:{thread_id}"
    raise ValueError("invalid_scope_key")


def compute_dedup_key(
    *,
    user_id: int,
    scope_key: str,
    layer: str,
    document_key: str,
    memory_type: str,
    normalized_key: str,
) -> str:
    raw = f"{user_id}|{scope_key}|{layer}|{document_key}|{memory_type}|{normalized_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_content_hash(*, content: str, structured_value: Any) -> str:
    canonical = {
        "content": normalize_text(content),
        "structured_value": structured_value or {},
    }
    raw = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def compute_normalized_key(*, memory_type: str, content: str, client_key: str | None = None) -> str:
    client = str(client_key or "").strip()
    if client and len(client) <= 128 and all(ch.isalnum() or ch in "._-" for ch in client):
        return client
    digest = hashlib.sha256(normalize_text(content).encode("utf-8")).hexdigest()[:16]
    prefix = "preference" if memory_type == "preference" else memory_type or "memory"
    return f"{prefix}.{digest}"


def hash_device_id(device_id: Any) -> str | None:
    if not device_id:
        return None
    return hashlib.sha256(str(device_id).encode("utf-8")).hexdigest()


def mutation_id_from_key(key: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(key))
    except (TypeError, ValueError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"spark-memory:{key}")


def title_from_content(content: str, title: str | None = None) -> str:
    cleaned = str(title or "").strip()[:MAX_TITLE_LENGTH]
    if cleaned:
        return cleaned
    return normalize_text(content)[:20]


def clamp_content(content: str) -> str:
    return normalize_text(content)[:MAX_CONTENT_CHARS]


def validate_layer_document(layer: str, document_key: str) -> None:
    if layer == MemoryLayer.L2 and document_key in L2_DOCUMENT_KEYS:
        return
    if layer == MemoryLayer.L3 and document_key in L3_DOCUMENT_KEYS:
        return
    raise ValueError("invalid_layer_document")


def validate_section_key(section_key: str, *, document_key: str) -> str:
    key = str(section_key or "general").strip() or "general"
    allowed = PREFERENCE_SECTION_KEYS if document_key == "preferences" else ALLOWED_SECTION_KEYS
    if key not in allowed:
        raise ValueError("invalid_section_key")
    return key


def is_effective_memory(memory: AIMemory, *, now=None) -> bool:
    now = now or timezone.now()
    if memory.is_deleted:
        return False
    if memory.status != "active":
        return False
    if memory.confirmation_status not in {"not_required", "confirmed"}:
        return False
    if memory.expires_at is not None and memory.expires_at <= now:
        return False
    return True
