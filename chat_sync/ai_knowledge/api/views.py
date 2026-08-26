from __future__ import annotations

from typing import Any

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.response import success_response

from ..services import (
    DocumentDeletedError,
    DocumentQueryService,
    DocumentSyncError,
    DocumentSyncService,
    KnowledgeBaseService,
    RevisionConflictError,
)
from .serializers import KnowledgeSyncPushRequestSerializer


class KnowledgeDefaultBaseView(APIView):
    """GET /api/v1/ai/knowledge/default/ —— 幂等获取或创建当前账号的默认个人知识库。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        base = KnowledgeBaseService.get_or_create_default(request.user)
        return success_response(
            {
                "id": str(base.id),
                "name": base.name,
                "kind": base.kind,
                "is_default": base.is_default,
                "revision": base.revision,
                "server_updated_at": base.server_updated_at.isoformat(),
            },
            msg="ok",
        )


class KnowledgeSyncPushView(APIView):
    """POST /api/v1/ai/knowledge/sync/push/ —— 批量幂等写入；单条冲突不阻断同批其它 mutation。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = KnowledgeSyncPushRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mutations = serializer.validated_data["mutations"]

        results = []
        for mutation in mutations:
            mutation_id = mutation["mutation_id"]
            document_id = mutation["document_id"]
            try:
                result = DocumentSyncService.apply_mutation(user=request.user, mutation=mutation)
                results.append(_ack_from_result(mutation_id, result))
            except DocumentSyncError as exc:
                results.append(_ack_from_error(mutation_id, document_id, exc))

        return success_response({"results": results}, msg="ok")


class KnowledgeSyncPullView(APIView):
    """GET /api/v1/ai/knowledge/sync/pull/ —— 增量拉取，游标仅在整页成功落地后才应推进（由客户端保证）。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        cursor = request.query_params.get("cursor")
        limit = _parse_limit(request.query_params.get("limit"))
        result = DocumentQueryService.pull(user=request.user, cursor=cursor, limit=limit)
        return success_response(result, msg="ok")


def _parse_limit(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _ack_from_result(mutation_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "mutation_id": str(mutation_id),
        "document_id": result.get("id"),
        "status": result.get("status", "accepted"),
        "replayed": bool(result.get("replayed", False)),
        "revision": result.get("revision"),
        "server_updated_at": result.get("server_updated_at"),
        "content_hash": result.get("content_hash"),
    }


def _ack_from_error(mutation_id: Any, document_id: Any, exc: DocumentSyncError) -> dict[str, Any]:
    is_conflict = isinstance(exc, (RevisionConflictError, DocumentDeletedError))
    ack: dict[str, Any] = {
        "mutation_id": str(mutation_id),
        "document_id": str(document_id),
        "status": "conflict" if is_conflict else "error",
        "code": exc.code,
    }
    if exc.snapshot is not None:
        ack["current_document"] = exc.snapshot
    return ack
