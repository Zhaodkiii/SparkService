from __future__ import annotations

from typing import Any

from django.db.models import Count, Q

from chat_sync.ai_knowledge.api.dto import index_version_to_dto, knowledge_base_detail, knowledge_base_summary
from chat_sync.ai_knowledge.constants import KNOWLEDGE_FILE_BUSINESS_TYPE
from chat_sync.ai_knowledge.errors import KnowledgeError
from chat_sync.ai_models.knowledge import KnowledgeBase, KnowledgeDocument, KnowledgeIndexStatus, KnowledgeIndexVersion
from chat_sync.ai_knowledge.services.payloads import decode_cursor, encode_cursor
from file_manager.models import ManagedFileBusinessRelation


class KnowledgeBaseQueryService:
    @staticmethod
    def list_bases(*, user, cursor: str | None = None, limit: int = 20, q: str = "", index_status: str = "") -> dict[str, Any]:
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
        if index_status:
            summaries = [item for item in summaries if item["index_status"] == index_status]
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
        stats = KnowledgeBaseQueryService._stats(base)
        latest = (
            KnowledgeIndexVersion.objects.filter(knowledge_base=base).order_by("-created_at").first()
        )
        return knowledge_base_detail(
            base,
            document_count=stats["document_count"],
            file_count=stats["file_count"],
            index_status=stats["index_status"],
            active_index_version=stats["active_index_version"],
            latest_index=index_version_to_dto(latest) if latest else None,
            documents_summary=stats["documents_summary"],
        )

    @staticmethod
    def summarize(base: KnowledgeBase) -> dict[str, Any]:
        stats = KnowledgeBaseQueryService._stats(base)
        return knowledge_base_summary(
            base,
            document_count=stats["document_count"],
            file_count=stats["file_count"],
            index_status=stats["index_status"],
            active_index_version=stats["active_index_version"],
        )

    @staticmethod
    def _stats(base: KnowledgeBase) -> dict[str, Any]:
        docs = KnowledgeDocument.objects.filter(knowledge_base=base, is_deleted=False)
        document_count = docs.count()
        status_rows = list(docs.values("index_state__status").annotate(total=Count("id")))
        counts = {row["index_state__status"] or KnowledgeIndexStatus.PENDING: row["total"] for row in status_rows}
        file_count = ManagedFileBusinessRelation.objects.filter(
            user=base.user,
            business_type=KNOWLEDGE_FILE_BUSINESS_TYPE,
            business_id=str(base.id),
            file__is_deleted=False,
        ).count()
        active = KnowledgeIndexVersion.objects.filter(knowledge_base=base, is_active=True).order_by("-created_at").first()
        index_status = KnowledgeBaseQueryService._aggregate_status(counts, document_count)
        return {
            "document_count": document_count,
            "file_count": file_count,
            "index_status": index_status,
            "active_index_version": (active.signature or str(active.id)[:16]) if active else None,
            "documents_summary": {
                "ready": counts.get(KnowledgeIndexStatus.READY, 0),
                "pending": counts.get(KnowledgeIndexStatus.PENDING, 0) + counts.get(KnowledgeIndexStatus.PROCESSING, 0) + counts.get(KnowledgeIndexStatus.STALE, 0) + counts.get(None, 0),
                "failed": counts.get(KnowledgeIndexStatus.FAILED, 0),
            },
        }

    @staticmethod
    def _aggregate_status(counts: dict[str | None, int], document_count: int) -> str:
        if document_count == 0:
            return KnowledgeIndexStatus.PENDING
        if counts.get(KnowledgeIndexStatus.FAILED, 0) and not counts.get(KnowledgeIndexStatus.READY, 0) and not counts.get(KnowledgeIndexStatus.PROCESSING, 0):
            return KnowledgeIndexStatus.FAILED
        if counts.get(KnowledgeIndexStatus.PROCESSING, 0) or counts.get(KnowledgeIndexStatus.PENDING, 0):
            return KnowledgeIndexStatus.PROCESSING
        if counts.get(KnowledgeIndexStatus.STALE, 0):
            return KnowledgeIndexStatus.STALE
        if counts.get(KnowledgeIndexStatus.FAILED, 0):
            return KnowledgeIndexStatus.FAILED
        if counts.get(KnowledgeIndexStatus.READY, 0) == document_count:
            return KnowledgeIndexStatus.READY
        return KnowledgeIndexStatus.PROCESSING
