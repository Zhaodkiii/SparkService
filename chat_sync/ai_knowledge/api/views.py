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


def _revision_from_request(request) -> int | None:
    raw = request.headers.get("If-Match") or request.data.get("revision")
    if raw is None or raw == "":
        return None
    try:
        return int(str(raw).strip('"'))
    except (TypeError, ValueError):
        return None


class KnowledgeBaseCollectionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from chat_sync.ai_knowledge.services.knowledge_base_query_service import KnowledgeBaseQueryService

        data = KnowledgeBaseQueryService.list_bases(
            user=request.user,
            cursor=request.query_params.get("cursor"),
            limit=_parse_limit(request.query_params.get("limit")) or 20,
            q=request.query_params.get("q") or "",
            index_status=request.query_params.get("index_status") or "",
        )
        return success_response(data, msg="ok")

    def post(self, request):
        from chat_sync.ai_knowledge.api.serializers import KnowledgeBaseCreateSerializer
        from chat_sync.ai_knowledge.services.command_idempotency import CommandIdempotencyService, command_request_hash
        from chat_sync.ai_knowledge.services.knowledge_base_query_service import KnowledgeBaseQueryService

        serializer = KnowledgeBaseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = request.headers.get("Idempotency-Key")
        request_hash = command_request_hash(serializer.validated_data)
        replay = CommandIdempotencyService.lookup(user=request.user, key=key, request_hash=request_hash)
        if replay is not None:
            return success_response(replay.response_snapshot, msg="ok", status_code=replay.status_code)
        base = KnowledgeBaseService.create(
            user=request.user,
            name=serializer.validated_data["name"],
            kind=serializer.validated_data.get("kind") or "personal",
            make_default=bool(serializer.validated_data.get("make_default")),
            retrieval_config=serializer.validated_data.get("retrieval_config"),
        )
        payload = KnowledgeBaseQueryService.detail(user=request.user, base_id=base.id)
        if key:
            CommandIdempotencyService.record(
                user=request.user, key=key, operation="create_base", request_hash=request_hash, status_code=201, response_snapshot=payload
            )
        return success_response(payload, msg="created", status_code=201)


class KnowledgeBaseDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, base_id):
        from chat_sync.ai_knowledge.services.knowledge_base_query_service import KnowledgeBaseQueryService

        return success_response(KnowledgeBaseQueryService.detail(user=request.user, base_id=base_id), msg="ok")

    def patch(self, request, base_id):
        from chat_sync.ai_knowledge.api.serializers import KnowledgeBaseUpdateSerializer
        from chat_sync.ai_knowledge.services.knowledge_base_query_service import KnowledgeBaseQueryService

        serializer = KnowledgeBaseUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        KnowledgeBaseService.update(
            user=request.user,
            base_id=base_id,
            revision=_revision_from_request(request),
            name=serializer.validated_data.get("name"),
            make_default=serializer.validated_data.get("make_default"),
            retrieval_config=serializer.validated_data.get("retrieval_config"),
        )
        return success_response(KnowledgeBaseQueryService.detail(user=request.user, base_id=base_id), msg="updated")

    def delete(self, request, base_id):
        KnowledgeBaseService.soft_delete(user=request.user, base_id=base_id, revision=_revision_from_request(request))
        return success_response({"id": str(base_id), "is_deleted": True}, msg="deleted")


class KnowledgeDocumentCollectionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, base_id):
        from chat_sync.ai_knowledge.services.document_command_service import DocumentCommandService

        data = DocumentCommandService.list_documents(
            user=request.user,
            base_id=base_id,
            cursor=request.query_params.get("cursor"),
            limit=_parse_limit(request.query_params.get("limit")) or 20,
        )
        return success_response(data, msg="ok")

    def post(self, request, base_id):
        from chat_sync.ai_knowledge.api.serializers import KnowledgeDocumentWriteSerializer
        from chat_sync.ai_knowledge.services.document_command_service import DocumentCommandService

        serializer = KnowledgeDocumentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = DocumentCommandService.create(
            user=request.user,
            base_id=base_id,
            title=serializer.validated_data.get("title") or "",
            content=serializer.validated_data.get("content") or "",
            scope=serializer.validated_data.get("scope") or "personal",
            source=serializer.validated_data.get("source") or "user",
        )
        return success_response(DocumentCommandService.to_detail(document, request.user), msg="created", status_code=201)


class KnowledgeDocumentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, document_id):
        from chat_sync.ai_knowledge.services.document_command_service import DocumentCommandService

        document = DocumentCommandService.get(user=request.user, document_id=document_id)
        return success_response(DocumentCommandService.to_detail(document, request.user), msg="ok")

    def patch(self, request, document_id):
        from chat_sync.ai_knowledge.api.serializers import KnowledgeDocumentWriteSerializer
        from chat_sync.ai_knowledge.errors import KnowledgeError
        from chat_sync.ai_knowledge.services.document_command_service import DocumentCommandService

        serializer = KnowledgeDocumentWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        revision = _revision_from_request(request)
        if revision is None:
            raise KnowledgeError("knowledge_payload_invalid", details={"field": "revision"})
        document = DocumentCommandService.update(
            user=request.user,
            document_id=document_id,
            revision=revision,
            title=serializer.validated_data.get("title"),
            content=serializer.validated_data.get("content"),
        )
        return success_response(DocumentCommandService.to_detail(document, request.user), msg="updated")

    def delete(self, request, document_id):
        from chat_sync.ai_knowledge.services.document_command_service import DocumentCommandService

        DocumentCommandService.delete(user=request.user, document_id=document_id, revision=_revision_from_request(request))
        return success_response({"id": str(document_id), "is_deleted": True}, msg="deleted")


class KnowledgeFileCollectionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, base_id):
        from chat_sync.ai_knowledge.services.file_service import KnowledgeFileService

        return success_response(KnowledgeFileService.list_files(user=request.user, base_id=base_id), msg="ok")

    def post(self, request, base_id):
        from django.conf import settings
        from chat_sync.ai_knowledge.api.serializers import KnowledgeFileBindSerializer
        from chat_sync.ai_knowledge.errors import KnowledgeError
        from chat_sync.ai_knowledge.services.file_service import KnowledgeFileService

        if not getattr(settings, "KNOWLEDGE_FILE_IMPORT_ENABLED", True):
            raise KnowledgeError("knowledge_file_unsupported")
        serializer = KnowledgeFileBindSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = KnowledgeFileService.bind(
            user=request.user,
            base_id=base_id,
            file_uuid=serializer.validated_data["file_uuid"],
            reuse=bool(serializer.validated_data.get("reuse")),
        )
        return success_response(payload, msg="accepted", status_code=202)


class KnowledgeFileDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, base_id, file_uuid):
        from chat_sync.ai_knowledge.services.file_service import KnowledgeFileService

        KnowledgeFileService.unbind(
            user=request.user,
            base_id=base_id,
            file_uuid=file_uuid,
            delete_document=str(request.query_params.get("delete_document") or "1") not in {"0", "false"},
        )
        return success_response({"file_uuid": str(file_uuid), "unbound": True}, msg="deleted")


class KnowledgeIndexVersionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, base_id):
        from chat_sync.ai_knowledge.api.dto import index_version_to_dto
        from chat_sync.ai_knowledge.services.knowledge_base_service import KnowledgeBaseService
        from chat_sync.ai_models.knowledge import KnowledgeIndexVersion

        KnowledgeBaseService.get_owned(user=request.user, base_id=base_id)
        rows = KnowledgeIndexVersion.objects.filter(knowledge_base_id=base_id).order_by("-created_at")[:50]
        return success_response({"items": [index_version_to_dto(item) for item in rows]}, msg="ok")


class KnowledgeIndexJobView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, base_id):
        from chat_sync.ai_knowledge.services.index_jobs import enqueue_base_rebuild
        from chat_sync.ai_knowledge.services.knowledge_base_service import KnowledgeBaseService

        KnowledgeBaseService.get_owned(user=request.user, base_id=base_id)
        job_id = enqueue_base_rebuild(str(base_id))
        return success_response({"job_id": job_id, "status": "pending"}, msg="accepted", status_code=202)


class KnowledgeSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from chat_sync.ai_knowledge.api.dto import citation_to_dto, relevance_label
        from chat_sync.ai_knowledge.api.serializers import KnowledgeSearchSerializer
        from chat_sync.ai_knowledge.retrieval.service import get_retrieval_port
        from chat_sync.ai_models.knowledge import KnowledgeBase

        serializer = KnowledgeSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        base_ids = [str(item) for item in (serializer.validated_data.get("knowledge_base_ids") or [])]
        if not base_ids:
            base_ids = [str(item) for item in KnowledgeBase.objects.filter(user=request.user, is_deleted=False).values_list("id", flat=True)[:20]]
        hits = get_retrieval_port().search(
            user=request.user,
            base_ids=base_ids,
            query=serializer.validated_data["query"],
            top_k=serializer.validated_data.get("top_k") or 8,
            threshold=serializer.validated_data.get("score_threshold") or 0.0,
        )
        citations = [
            citation_to_dto(
                citation_id=f"cite_{index}",
                knowledge_base_id=str(item.metadata.get("knowledge_base_id") or ""),
                knowledge_base_name=str(item.metadata.get("knowledge_base_name") or ""),
                document_id=item.document_id,
                document_title=item.title,
                chunk_id=item.chunk_id,
                chunk_revision=item.document_revision,
                index_version=item.index_version,
                snippet=item.content,
                relevance=relevance_label(float(item.metadata.get("score") or 0)),
            )
            for index, item in enumerate(hits, start=1)
        ]
        return success_response({"items": citations, "hit_count": len(citations)}, msg="ok")
