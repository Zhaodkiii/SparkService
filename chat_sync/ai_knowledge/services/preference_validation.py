from __future__ import annotations

from typing import Any

from chat_sync.ai_models.knowledge import KnowledgeBase


def validate_knowledge_base_ids(user, values: list[Any] | None) -> dict[str, Any]:
    ordered: list[str] = []
    seen: set[str] = set()
    rejected: list[dict[str, str]] = []
    for raw in values or []:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        base = KnowledgeBase.objects.filter(user=user, id=text).first()
        if base is None:
            rejected.append({"id": text, "reason": "knowledge_base_not_found"})
            continue
        if base.is_deleted:
            rejected.append({"id": text, "reason": "knowledge_base_deleted"})
            continue
        ordered.append(str(base.id))
    return {"knowledge_bases": ordered, "rejected_ids": rejected}
