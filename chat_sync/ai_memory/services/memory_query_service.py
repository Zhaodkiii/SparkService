from __future__ import annotations

from typing import Any

from django.db.models import Q
from django.utils import timezone

from chat_sync.ai_memory.constants import (
    DEFAULT_READ_TOKEN_BUDGET,
    DEFAULT_RECALL_COUNT,
    HARD_READ_TOKEN_BUDGET,
    MAX_RECALL_COUNT,
    PULL_DEFAULT_LIMIT,
    PULL_MAX_LIMIT,
)
from chat_sync.ai_memory.errors import MemoryError
from chat_sync.ai_memory.services.payloads import decode_cursor, encode_cursor, memory_to_snapshot
from chat_sync.ai_models.memory import AIMemory, MemoryLayer, MemoryScope
from medical.services.member_permission_service import MemberPermissionDenied


class MemoryQueryService:
    @staticmethod
    def pull(*, user, cursor: str | None, limit: int | None) -> dict[str, Any]:
        effective_limit = _normalize_limit(limit)
        cursor_dt, cursor_tie = decode_cursor(cursor)
        queryset = AIMemory.objects.filter(user=user)
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
            "items": [memory_to_snapshot(item) for item in page],
            "next_cursor": next_cursor,
            "has_more": has_more,
            "server_time": timezone.now().isoformat(),
        }

    @staticmethod
    def list_entries(
        *,
        user,
        layer: str | None = None,
        document_key: str | None = None,
        scope: str | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit or 50), 100))
        queryset = AIMemory.objects.filter(user=user, is_deleted=False)
        if layer:
            queryset = queryset.filter(layer=layer)
        if document_key:
            queryset = queryset.filter(document_key=document_key)
        if scope:
            queryset = queryset.filter(scope=scope)
        if status:
            queryset = queryset.filter(status=status)
        cursor_dt, cursor_tie = decode_cursor(cursor)
        if cursor_dt is not None and cursor_tie is not None:
            queryset = queryset.filter(Q(server_updated_at__lt=cursor_dt) | Q(server_updated_at=cursor_dt, id__lt=cursor_tie))
        rows = list(queryset.order_by("-server_updated_at", "-id")[: limit + 1])
        page = rows[:limit]
        last = page[-1] if page else None
        next_cursor = (
            encode_cursor(server_updated_at=last.server_updated_at, tie_breaker=str(last.id)) if last is not None else None
        )
        return {
            "items": [memory_to_snapshot(item) for item in page],
            "next_cursor": next_cursor,
            "has_more": len(rows) > limit,
        }

    @staticmethod
    def get_entry(*, user, memory_id) -> dict[str, Any]:
        memory = AIMemory.objects.filter(user=user, id=memory_id).first()
        if memory is None or memory.is_deleted:
            raise MemoryError("memory_not_found")
        return memory_to_snapshot(memory)

    @staticmethod
    def visible_l3_queryset(*, user, member_id: int | None = None):
        now = timezone.now()
        queryset = AIMemory.objects.filter(
            user=user,
            is_deleted=False,
            status="active",
            confirmation_status__in=["not_required", "confirmed"],
            layer=MemoryLayer.L3,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        scope_filter = Q(scope=MemoryScope.ACCOUNT, scope_key="account")
        if member_id is not None and _can_view_member(user, member_id):
            scope_filter = scope_filter | Q(scope=MemoryScope.MEMBER, member_id=member_id)
        return queryset.filter(scope_filter)

    @staticmethod
    def has_visible_l3(*, user, member_id: int | None = None) -> bool:
        return MemoryQueryService.visible_l3_queryset(user=user, member_id=member_id).exists()

    @staticmethod
    def recall_l3(*, user, member_id: int | None = None, max_count: int | None = None) -> list[AIMemory]:
        limit = min(int(max_count or DEFAULT_RECALL_COUNT), MAX_RECALL_COUNT)
        rows = list(MemoryQueryService.visible_l3_queryset(user=user, member_id=member_id))
        rows.sort(key=lambda item: (_recall_priority(item, member_id), 0 if item.is_pinned else 1, -(item.revision or 0)))
        seen_keys: set[str] = set()
        unique: list[AIMemory] = []
        for item in rows:
            key = item.normalized_key
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique.append(item)
            if len(unique) >= limit:
                break
        return unique


def clip_recall_rows(rows: list[AIMemory], *, token_budget: int = DEFAULT_READ_TOKEN_BUDGET) -> tuple[list[AIMemory], bool]:
    budget = max(1, min(int(token_budget or DEFAULT_READ_TOKEN_BUDGET), HARD_READ_TOKEN_BUDGET))
    used = 0
    kept: list[AIMemory] = []
    trimmed = False
    for item in rows:
        cost = max(1, (len(item.content or "") + 24) // 4)
        if used + cost > budget:
            trimmed = True
            break
        kept.append(item)
        used += cost
    return kept, trimmed


def _recall_priority(memory: AIMemory, member_id: int | None) -> int:
    if memory.document_key == "preferences":
        return 0
    if memory.scope == MemoryScope.MEMBER and memory.document_key == "profile" and memory.member_id == member_id:
        return 1
    if memory.document_key == "recent":
        return 2
    if memory.document_key == "scope":
        return 3
    if memory.document_key == "profile":
        return 4
    return 5


def _can_view_member(user, member_id: int) -> bool:
    try:
        from medical.services.member_permission_gate import MemberPermissionGate

        MemberPermissionGate.require_access(user, int(member_id))
        return True
    except MemberPermissionDenied:
        return False
    except Exception:
        return False


def _normalize_limit(limit: int | None) -> int:
    if not limit or limit <= 0:
        return PULL_DEFAULT_LIMIT
    return min(limit, PULL_MAX_LIMIT)
