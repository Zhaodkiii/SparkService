from __future__ import annotations

import uuid
from typing import Any

from chat_sync.ai_memory.errors import MemoryError
from chat_sync.ai_memory.services.keys import mutation_id_from_key
from chat_sync.ai_memory.services.memory_query_service import MemoryQueryService
from chat_sync.ai_memory.services.memory_sync_service import MemorySyncError, MemorySyncService
from chat_sync.ai_memory.services.payloads import memory_to_snapshot
from chat_sync.ai_models.memory import AIMemory, MemoryLayer, MemoryMutationOperation, MemoryScope


class MemoryCommandService:
    """HTTP create/read/update/delete for hand-authored preference entries."""

    @staticmethod
    def create(*, user, payload: dict[str, Any], idempotency_key: str | None = None) -> dict[str, Any]:
        memory_id = payload.get("id") or uuid.uuid4()
        mutation_id = mutation_id_from_key(idempotency_key) if idempotency_key else uuid.uuid4()
        body = {
            "scope": MemoryScope.ACCOUNT,
            "layer": MemoryLayer.L3,
            "document_key": "preferences",
            "section_key": payload.get("section_key") or "answer_style",
            "memory_type": payload.get("memory_type") or "preference",
            "normalized_key": payload.get("normalized_key"),
            "title": payload.get("title") or "",
            "content": payload.get("content") or "",
            "structured_value": payload.get("structured_value") or {},
            "source": "user",
            "sensitivity": payload.get("sensitivity") or "normal",
            "is_pinned": bool(payload.get("is_pinned") or False),
        }
        result = _apply(
            user=user,
            mutation={
                "mutation_id": mutation_id,
                "memory_id": memory_id,
                "operation": MemoryMutationOperation.CREATE,
                "memory": body,
            },
        )
        if result.get("status") == "conflict":
            raise MemoryError(
                "memory_duplicate_key",
                details={"snapshot": result.get("snapshot"), "memory_id": result.get("memory_id")},
            )
        return result["snapshot"]

    @staticmethod
    def update(*, user, memory_id, revision: int | None, payload: dict[str, Any]) -> dict[str, Any]:
        if revision is None:
            raise MemoryError("memory_revision_required")
        memory = _require_owned(user, memory_id)
        merged = memory_to_snapshot(memory)
        for key in ("title", "content", "structured_value", "is_pinned", "section_key", "normalized_key", "sensitivity"):
            if key in payload and payload[key] is not None:
                merged[key] = payload[key]
        result = _apply(
            user=user,
            mutation={
                "mutation_id": uuid.uuid4(),
                "memory_id": memory_id,
                "operation": MemoryMutationOperation.UPDATE,
                "base_revision": revision,
                "memory": merged,
            },
        )
        return result["snapshot"]

    @staticmethod
    def delete(*, user, memory_id, revision: int | None) -> dict[str, Any]:
        if revision is None:
            raise MemoryError("memory_revision_required")
        result = _apply(
            user=user,
            mutation={
                "mutation_id": uuid.uuid4(),
                "memory_id": memory_id,
                "operation": MemoryMutationOperation.DELETE,
                "base_revision": revision,
            },
        )
        return result["snapshot"]

    @staticmethod
    def get(*, user, memory_id) -> dict[str, Any]:
        return MemoryQueryService.get_entry(user=user, memory_id=memory_id)


def _require_owned(user, memory_id) -> AIMemory:
    memory = AIMemory.objects.filter(user=user, id=memory_id).first()
    if memory is None or memory.is_deleted:
        raise MemoryError("memory_not_found")
    return memory


def _apply(*, user, mutation: dict[str, Any]) -> dict[str, Any]:
    try:
        return MemorySyncService.apply_mutation(user=user, mutation=mutation, actor="user")
    except MemorySyncError as exc:
        details: dict[str, Any] = {}
        if exc.snapshot is not None:
            details["snapshot"] = exc.snapshot
        raise MemoryError(exc.code, details=details or None) from exc
