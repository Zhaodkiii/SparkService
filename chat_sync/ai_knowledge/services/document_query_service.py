from __future__ import annotations

from typing import Any

from django.db.models import Q

from chat_sync.ai_models.knowledge import KnowledgeDocument

from .payloads import decode_cursor, document_to_payload, encode_cursor

DEFAULT_LIMIT = 100
MAX_LIMIT = 200


class DocumentQueryService:
    """Pull 查询：`(server_updated_at, id)` 稳定排序 + opaque cursor；墓碑与正常文档同一数组返回。"""

    @staticmethod
    def pull(*, user, cursor: str | None, limit: int | None) -> dict[str, Any]:
        effective_limit = _normalize_limit(limit)
        cursor_dt, cursor_tie = decode_cursor(cursor)

        queryset = KnowledgeDocument.objects.filter(user=user)
        if cursor_dt is not None and cursor_tie is not None:
            queryset = queryset.filter(Q(server_updated_at__gt=cursor_dt) | Q(server_updated_at=cursor_dt, id__gt=cursor_tie))
        elif cursor_dt is not None:
            queryset = queryset.filter(server_updated_at__gt=cursor_dt)

        rows = list(queryset.order_by("server_updated_at", "id")[: effective_limit + 1])
        has_more = len(rows) > effective_limit
        page = rows[:effective_limit]
        last = page[-1] if page else None
        next_cursor = (
            encode_cursor(server_updated_at=last.server_updated_at, tie_breaker=str(last.id)) if last is not None else cursor
        )
        return {
            "cursor": next_cursor,
            "has_more": has_more,
            "documents": [document_to_payload(doc) for doc in page],
        }


def _normalize_limit(limit: int | None) -> int:
    if not limit or limit <= 0:
        return DEFAULT_LIMIT
    return min(limit, MAX_LIMIT)
