from __future__ import annotations

from typing import Any

from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeIndexStatus


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


def freeze_knowledge_bases(user, values: list[Any] | None) -> list[dict[str, Any]]:
    validated = validate_knowledge_base_ids(user, values)
    frozen: list[dict[str, Any]] = []
    for base_id in validated["knowledge_bases"]:
        base = KnowledgeBase.objects.filter(user=user, id=base_id, is_deleted=False).first()
        if base is None:
            continue
        from chat_sync.ai_models.knowledge import KnowledgeIndexVersion

        active = KnowledgeIndexVersion.objects.filter(knowledge_base=base, is_active=True).order_by("-created_at").first()
        frozen.append(
            {
                "id": str(base.id),
                "name": base.name,
                "revision": base.revision,
                "index_status": _base_index_status(base),
                "active_index_version": (active.signature if active else None),
                "retrieval_eligible": _base_index_status(base) == KnowledgeIndexStatus.READY,
            }
        )
    return frozen


def _base_index_status(base: KnowledgeBase) -> str:
    from chat_sync.ai_knowledge.services.knowledge_base_query_service import KnowledgeBaseQueryService

    return KnowledgeBaseQueryService._stats(base)["index_status"]
