from __future__ import annotations

from typing import Any

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.response import success_response

from chat_sync.ai_memory.api.serializers import MemoryEntryWriteSerializer, MemorySyncPushRequestSerializer
from chat_sync.ai_memory.services.memory_command_service import MemoryCommandService
from chat_sync.ai_memory.services.memory_query_service import MemoryQueryService
from chat_sync.ai_memory.services.memory_sync_service import MemorySyncError, MemorySyncService


class MemoryEntryCollectionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = MemoryQueryService.list_entries(
            user=request.user,
            layer=request.query_params.get("layer") or None,
            document_key=request.query_params.get("document_key") or None,
            scope=request.query_params.get("scope") or None,
            status=request.query_params.get("status") or None,
            cursor=request.query_params.get("cursor"),
            limit=_parse_limit(request.query_params.get("limit")) or 50,
        )
        return success_response(data, msg="ok")

    def post(self, request):
        serializer = MemoryEntryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        if not payload.get("content"):
            from chat_sync.ai_memory.errors import MemoryError

            raise MemoryError("memory_payload_invalid", details={"field": "content"})
        data = MemoryCommandService.create(
            user=request.user,
            payload=payload,
            idempotency_key=request.headers.get("Idempotency-Key"),
        )
        return success_response(data, msg="created", status_code=201)


class MemoryEntryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, memory_id):
        return success_response(MemoryCommandService.get(user=request.user, memory_id=memory_id), msg="ok")

    def patch(self, request, memory_id):
        serializer = MemoryEntryWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        revision = payload.get("revision")
        if revision is None:
            revision = _revision_from_request(request)
        data = MemoryCommandService.update(
            user=request.user,
            memory_id=memory_id,
            revision=revision,
            payload=payload,
        )
        return success_response(data, msg="updated")

    def delete(self, request, memory_id):
        revision = _revision_from_request(request)
        data = MemoryCommandService.delete(user=request.user, memory_id=memory_id, revision=revision)
        return success_response(data, msg="deleted")


class MemorySyncPushView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MemorySyncPushRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results = []
        for mutation in serializer.validated_data["mutations"]:
            mutation_id = mutation["mutation_id"]
            memory_id = mutation["memory_id"]
            try:
                result = MemorySyncService.apply_mutation(user=request.user, mutation=mutation)
                results.append(_ack_from_result(mutation_id, result))
            except MemorySyncError as exc:
                results.append(_ack_from_error(mutation_id, memory_id, exc))
        return success_response({"results": results}, msg="ok")


class MemorySyncPullView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        result = MemoryQueryService.pull(
            user=request.user,
            cursor=request.query_params.get("cursor"),
            limit=_parse_limit(request.query_params.get("limit")),
        )
        return success_response(result, msg="ok")


def _revision_from_request(request) -> int | None:
    raw = request.query_params.get("revision") or request.data.get("revision")
    if raw is None or raw == "":
        return None
    try:
        return int(str(raw).strip('"'))
    except (TypeError, ValueError):
        return None


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
        "memory_id": result.get("memory_id"),
        "status": result.get("status", "accepted"),
        "replayed": bool(result.get("replayed", False)),
        "snapshot": result.get("snapshot") or {},
        "resolution": result.get("resolution"),
        "reason_code": result.get("reason_code"),
        "revision": result.get("revision"),
    }


def _ack_from_error(mutation_id: Any, memory_id: Any, exc: MemorySyncError) -> dict[str, Any]:
    is_conflict = exc.status_code == 409 and exc.code != "memory_mutation_reused"
    return {
        "mutation_id": str(mutation_id),
        "memory_id": str(memory_id),
        "status": "conflict" if is_conflict else "error",
        "replayed": False,
        "snapshot": exc.snapshot or {},
        "resolution": "server_wins" if is_conflict and exc.snapshot is not None else None,
        "reason_code": exc.reason_code or exc.code,
    }
