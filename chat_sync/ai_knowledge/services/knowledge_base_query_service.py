from __future__ import annotations

from typing import Any

from django.db.models import Q

from chat_sync.ai_knowledge.api.dto import knowledge_base_detail, knowledge_base_summary
from chat_sync.ai_knowledge.errors import KnowledgeError
from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeDocument
from chat_sync.ai_knowledge.services.payloads import decode_cursor, encode_cursor


class KnowledgeBaseQueryService:
    @staticmethod
    def list_bases(*, user, cursor: str | None = None, limit: int = 20, q: str = "") -> dict[str, Any]:
        limit = max(1, min(int(limit or 20), 50))
        queryset = KnowledgeBase.objects.filter(user=user, is_deleted=False)
        if q:
            queryset = queryset.filter(name__icontains=q.strip()[:64])
        cursor_dt, cursor_tie = decode_cursor(cursor)
        if cursor_dt is not None and cursor_tie is not None:
            queryset = queryset.filter(Q(server_updated_at__lt=cursor_dt) | Q(server_updated_at=cursor_dt, id__lt=cursor_tie))
        rows = list(queryset.order_by("-server_updated_at", "-id")[: limit + 1])
        page = rows[:limit]
        summaries = [KnowledgeBaseQueryService.summarize(base) for base in page]
        last = page[-1] if page else None
        next_cursor = (
            encode_cursor(server_updated_at=last.server_updated_at, tie_breaker=str(last.id)) if last is not None and len(rows) > limit else None
        )
        return {"items": summaries, "next_cursor": next_cursor}

    @staticmethod
    def detail(*, user, base_id) -> dict[str, Any]:
        base = KnowledgeBase.objects.filter(user=user, id=base_id, is_deleted=False).first()
        if base is None:
            raise KnowledgeError("knowledge_base_not_found", details={"resource_id": str(base_id)})
        return knowledge_base_detail(base, document_count=KnowledgeBaseQueryService._document_count(base))

    @staticmethod
    def summarize(base: KnowledgeBase) -> dict[str, Any]:
        return knowledge_base_summary(base, document_count=KnowledgeBaseQueryService._document_count(base))

    @staticmethod
    def _document_count(base: KnowledgeBase) -> int:
        return KnowledgeDocument.objects.filter(knowledge_base=base, is_deleted=False).count()
