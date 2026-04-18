import json
import logging
import uuid
import base64
from datetime import datetime, timezone

from django.db import transaction
from django.db.models import Max, Q
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from chat_sync.events import ChatSyncNotifier
from chat_sync.models import ChatMessage, ChatThread
from chat_sync.serializers import (
    ChatPushRequestSerializer,
    ChatThreadDeleteRequestSerializer,
)
from common.exceptions import APIError
from common.response import success_response

logger = logging.getLogger("chat_sync.sync")


def _json_for_log(obj) -> str:
    """将请求/响应体序列化为单行 JSON，便于检索；UUID、datetime 等用 default=str。"""
    return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))


def _encode_cursor(*, dt: datetime, tie_breaker: str) -> str:
    """
    统一游标编码（v2）：
    - ts: server_updated_at 的 ISO8601（UTC）
    - id: 同一时间戳内的稳定二级排序键（thread.id 或 message.id）
    """
    payload = {"ts": dt.astimezone(timezone.utc).isoformat(), "id": tie_breaker}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"v2:{token}"


def _decode_cursor(cursor: str | None) -> tuple[datetime | None, str | None]:
    """
    统一游标解码：
    - 新版：v2:<base64(json)>
    - 兜底：旧版纯时间戳字符串（无 tie-breaker）
    """
    if cursor is None or cursor == "":
        return None, None

    if cursor.startswith("v2:"):
        token = cursor[3:]
        try:
            padding = "=" * (-len(token) % 4)
            raw = base64.urlsafe_b64decode((token + padding).encode("ascii"))
            payload = json.loads(raw.decode("utf-8"))
            ts = payload.get("ts")
            tie = payload.get("id")
            dt = _normalize_cursor(ts)
            if dt is None:
                return None, None
            return dt, str(tie) if tie is not None else None
        except Exception:
            return None, None

    # 兼容旧 cursor，仅包含时间戳。
    return _normalize_cursor(cursor), None


def _normalize_cursor(cursor: str | None) -> datetime | None:
    if cursor is None or cursor == "":
        return None

    as_datetime = parse_datetime(cursor)
    if as_datetime is not None:
        if as_datetime.tzinfo is None:
            return as_datetime.replace(tzinfo=timezone.utc)
        return as_datetime

    try:
        value = float(cursor)
        if value > 10_000_000_000:
            value = value / 1000
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except Exception:
        return None


def _metadata_to_public_fields(metadata: dict) -> dict:
    return {
        "attachments": metadata.get("attachments") or [],
        "reasoning_content": metadata.get("reasoning_content"),
        "reasoning_duration_ms": metadata.get("reasoning_duration_ms"),
        "reasoning_expanded": metadata.get("reasoning_expanded"),
        "reasoning_visibility": metadata.get("reasoning_visibility"),
    }

def _extract_image_delivery_mode_from_attachments(attachments: list) -> str | None:
    for item in attachments:
        if isinstance(item, dict) is False:
            continue
        if item.get("type") not in ("image_url", "image"):
            continue
        raw = item.get("imageDeliveryModeRaw")
        if isinstance(raw, str):
            trimmed = raw.strip()
            if trimmed:
                return trimmed
    return None


def _to_payload(message: ChatMessage) -> dict:
    metadata = message.metadata or {}
    public_fields = _metadata_to_public_fields(metadata)
    return {
        "thread_id": str(message.thread_id),
        "role": message.role,
        "kind": message.kind,
        "content": message.content,
        "client_message_id": str(message.client_message_id),
        "server_message_id": message.server_message_id,
        "delivery_state": message.delivery_state,
        "created_at": message.created_at.isoformat(),
        "server_updated_at": message.server_updated_at.isoformat(),
        "tombstone": message.tombstone,
        "attachments": public_fields["attachments"],
        "reasoning_content": public_fields["reasoning_content"],
        "reasoning_duration_ms": public_fields["reasoning_duration_ms"],
        "reasoning_expanded": public_fields["reasoning_expanded"],
        "reasoning_visibility": public_fields["reasoning_visibility"],
    }


def _to_thread_payload(thread: ChatThread) -> dict:
    return {
        "thread_id": str(thread.id),
        "title": thread.title,
        "scenario": thread.scenario,
        "image_delivery_mode": thread.image_delivery_mode,
        "patient_id": str(thread.patient_id) if thread.patient_id else None,
        "is_deleted": thread.is_deleted,
        "deleted_at": thread.deleted_at.isoformat() if thread.deleted_at else None,
        "updated_at": thread.updated_at.isoformat(),
        "server_updated_at": thread.server_updated_at.isoformat(),
    }


class ChatSyncPushView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_id = request.headers.get("X-Request-ID", "-")
        payload_data = _resolve_push_payload(request)
        serializer = ChatPushRequestSerializer(data=payload_data)
        serializer.is_valid(raise_exception=True)

        messages_payload = serializer.validated_data["messages"]
        logger.info(
            "chat push payload request_id=%s user_id=%s content_type=%s body=%s",
            request_id,
            getattr(request.user, "id", "-"),
            request.content_type,
            _json_for_log(serializer.validated_data),
        )
        logger.info(
            "chat push start request_id=%s user_id=%s count=%s content_type=%s",
            request_id,
            getattr(request.user, "id", "-"),
            len(messages_payload),
            request.content_type,
        )
        if not messages_payload:
            logger.info("chat push skipped(empty) request_id=%s", request_id)
            return success_response({"messages": []}, msg="ok", code=0)

        result = []
        with transaction.atomic():
            for payload in messages_payload:
                thread, _ = ChatThread.objects.get_or_create(
                    id=payload["thread_id"],
                    defaults={
                        "user": request.user,
                        "title": "New Chat",
                        "scenario": ChatThread.Scenario.CHAT,
                    },
                )
                if thread.user_id != request.user.id:
                    raise APIError(
                        msg="thread_id_conflict",
                        code=40901,
                        status_code=409,
                        details={"thread_id": str(payload["thread_id"])},
                    )

                # 客户端若在已软删线程继续发送，默认视为“恢复线程”。
                if thread.is_deleted:
                    thread.is_deleted = False
                    thread.deleted_at = None

                server_message_id = payload.get("server_message_id")
                if server_message_id is None or server_message_id == "":
                    server_message_id = str(uuid.uuid4())

                metadata = {
                    "attachments": payload.get("attachments") or [],
                    "reasoning_content": payload.get("reasoning_content"),
                    "reasoning_duration_ms": payload.get("reasoning_duration_ms"),
                    "reasoning_expanded": payload.get("reasoning_expanded"),
                    "reasoning_visibility": payload.get("reasoning_visibility"),
                }
                attachment_mode = _extract_image_delivery_mode_from_attachments(metadata["attachments"])
                if attachment_mode:
                    thread.image_delivery_mode = attachment_mode

                defaults = {
                    "thread": thread,
                    "user": request.user,
                    "role": payload["role"],
                    "kind": payload["kind"],
                    "content": payload["content"],
                    "server_message_id": server_message_id,
                    "delivery_state": _normalize_delivery_state(payload["delivery_state"]),
                    "created_at": payload["created_at"],
                    "tombstone": payload.get("tombstone", False),
                    "metadata": metadata,
                }

                message, created = ChatMessage.objects.get_or_create(
                    user=request.user,
                    client_message_id=payload["client_message_id"],
                    defaults=defaults,
                )

                if not created:
                    message.thread = thread
                    message.role = payload["role"]
                    message.kind = payload["kind"]
                    message.content = payload["content"]
                    if payload.get("server_message_id"):
                        message.server_message_id = payload["server_message_id"]
                    message.delivery_state = _normalize_delivery_state(payload["delivery_state"])
                    message.created_at = payload["created_at"]
                    message.tombstone = payload.get("tombstone", False)
                    message.metadata = metadata
                    message.save(
                        update_fields=[
                            "thread",
                            "role",
                            "kind",
                            "content",
                            "server_message_id",
                            "delivery_state",
                            "created_at",
                            "tombstone",
                            "metadata",
                            "server_updated_at",
                        ]
                    )

                thread.updated_at = datetime.now(tz=timezone.utc)
                thread.save(
                    update_fields=[
                        "updated_at",
                        "server_updated_at",
                        "is_deleted",
                        "deleted_at",
                        "image_delivery_mode",
                    ]
                )
                result.append(_to_payload(message))

        logger.info(
            "chat push success request_id=%s user_id=%s accepted=%s",
            request_id,
            request.user.id,
            len(result),
        )

        return success_response({"messages": result}, msg="ok", code=0)


class ChatSyncThreadHeadView(APIView):
    """返回指定会话在服务端最新消息时间戳（仅未软删线程可查询）。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        thread_id_raw = request.query_params.get("thread_id")
        if not thread_id_raw:
            raise APIError(msg="thread_id_required", code=40031, status_code=400)

        try:
            thread_uuid = uuid.UUID(thread_id_raw)
        except ValueError as exc:
            raise APIError(msg="invalid_thread_id", code=40032, status_code=400) from exc

        thread = ChatThread.objects.filter(id=thread_uuid, user=request.user, is_deleted=False).first()
        if thread is None:
            raise APIError(msg="thread_not_found", code=40401, status_code=404)

        max_dt = ChatMessage.objects.filter(user=request.user, thread_id=thread_uuid).aggregate(m=Max("server_updated_at"))["m"]

        return success_response(
            {
                "thread_id": str(thread.id),
                "last_server_updated_at": max_dt.isoformat() if max_dt is not None else None,
            },
            msg="ok",
            code=0,
        )


class ChatSyncThreadPullView(APIView):
    """按线程维度拉增量，用于最小带宽同步会话列表与软删除状态。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        cursor = request.query_params.get("cursor")
        cursor_dt, cursor_tie = _decode_cursor(cursor)
        limit = _normalize_limit(request.query_params.get("limit"), default=100, max_value=200)

        queryset = ChatThread.objects.filter(user=request.user)
        if cursor_dt is not None and cursor_tie is not None:
            queryset = queryset.filter(
                Q(server_updated_at__gt=cursor_dt) | Q(server_updated_at=cursor_dt, id__gt=cursor_tie)
            )
        elif cursor_dt is not None:
            queryset = queryset.filter(server_updated_at__gt=cursor_dt)

        threads = list(queryset.order_by("server_updated_at", "id")[: limit + 1])
        has_more = len(threads) > limit
        page = threads[:limit]
        last = page[-1] if page else None
        payload = [_to_thread_payload(item) for item in page]
        next_cursor = (
            _encode_cursor(dt=last.server_updated_at, tie_breaker=str(last.id))
            if last is not None
            else cursor
        )

        logger.info(
            "chat thread-pull success request_id=%s user_id=%s input_cursor=%s next_cursor=%s count=%s has_more=%s",
            request.headers.get("X-Request-ID", "-"),
            request.user.id,
            cursor,
            next_cursor,
            len(page),
            has_more,
        )
        return success_response({"cursor": next_cursor, "threads": payload, "has_more": has_more}, msg="ok", code=0)


class ChatSyncThreadDeleteView(APIView):
    """客户端删除线程后上送服务端：线程采用软删除。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatThreadDeleteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        requested_ids = serializer.validated_data["thread_ids"]
        logger.info(
            "chat thread-delete payload request_id=%s user_id=%s body=%s",
            request.headers.get("X-Request-ID", "-"),
            request.user.id,
            _json_for_log(serializer.validated_data),
        )
        now = datetime.now(tz=timezone.utc)

        queryset = ChatThread.objects.filter(user=request.user, id__in=requested_ids)
        rows = list(queryset)
        if not rows:
            return success_response({"thread_ids": []}, msg="ok", code=0)

        changed_ids = []
        with transaction.atomic():
            for thread in rows:
                if thread.is_deleted:
                    continue
                thread.is_deleted = True
                thread.deleted_at = now
                thread.updated_at = now
                thread.save(update_fields=["is_deleted", "deleted_at", "updated_at", "server_updated_at"])
                changed_ids.append(thread.id)

        if changed_ids:
            latest = ChatThread.objects.filter(user=request.user, id__in=changed_ids).aggregate(m=Max("server_updated_at"))["m"]
            if latest is not None:
                ChatSyncNotifier.notify_user_sync(
                    user_id=request.user.id,
                    cursor=latest.isoformat(),
                    message_ids=[],
                )

        logger.info(
            "chat thread-delete success request_id=%s user_id=%s requested=%s changed=%s",
            request.headers.get("X-Request-ID", "-"),
            request.user.id,
            len(requested_ids),
            len(changed_ids),
        )
        return success_response({"thread_ids": [str(i) for i in changed_ids]}, msg="ok", code=0)


class ChatSyncPullView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cursor = request.query_params.get("cursor")
        cursor_dt, cursor_tie = _decode_cursor(cursor)
        limit = _normalize_limit(request.query_params.get("limit"), default=200, max_value=200)

        queryset = ChatMessage.objects.filter(user=request.user, thread__is_deleted=False)

        thread_id_raw = request.query_params.get("thread_id")
        if thread_id_raw:
            try:
                thread_uuid = uuid.UUID(thread_id_raw)
            except ValueError as exc:
                raise APIError(msg="invalid_thread_id", code=40032, status_code=400) from exc
            if not ChatThread.objects.filter(id=thread_uuid, user=request.user, is_deleted=False).exists():
                raise APIError(msg="thread_not_found", code=40401, status_code=404)
            queryset = queryset.filter(thread_id=thread_uuid)

        if cursor_dt is not None and cursor_tie is not None:
            queryset = queryset.filter(
                Q(server_updated_at__gt=cursor_dt) | Q(server_updated_at=cursor_dt, id__gt=cursor_tie)
            )
        elif cursor_dt is not None:
            queryset = queryset.filter(server_updated_at__gt=cursor_dt)

        messages = list(queryset.order_by("server_updated_at", "id")[: limit + 1])
        has_more = len(messages) > limit
        page = messages[:limit]
        last = page[-1] if page else None
        payload = [_to_payload(item) for item in page]
        next_cursor = (
            _encode_cursor(dt=last.server_updated_at, tie_breaker=str(last.id))
            if last is not None
            else cursor
        )
        logger.info(
            "chat pull success request_id=%s user_id=%s input_cursor=%s next_cursor=%s count=%s has_more=%s",
            request.headers.get("X-Request-ID", "-"),
            request.user.id,
            cursor,
            next_cursor,
            len(payload),
            has_more,
        )
        return success_response({"cursor": next_cursor, "messages": payload, "has_more": has_more}, msg="ok", code=0)


def _normalize_delivery_state(state: str) -> str:
    if state in (ChatMessage.DeliveryState.PENDING, ChatMessage.DeliveryState.SENDING):
        return ChatMessage.DeliveryState.SENT
    if state in ChatMessage.DeliveryState.values:
        return state
    return ChatMessage.DeliveryState.SENT


def _normalize_limit(raw: str | None, default: int, max_value: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(1, min(max_value, value))


def _resolve_push_payload(request):
    """
    首选 DRF 解析后的 request.data。
    若客户端误发 Content-Type（如 form-urlencoded）但 body 实际是 JSON，则回退到原始 body 解析，
    避免出现 messages required 的误判。
    """
    if isinstance(request.data, dict) and "messages" in request.data:
        return request.data

    raw_text = request.body.decode("utf-8", errors="ignore")
    if not raw_text:
        return request.data

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning(
            "chat push invalid json body request_id=%s content_type=%s body_preview=%s",
            request.headers.get("X-Request-ID", "-"),
            request.content_type,
            raw_text[:256],
        )
        return request.data

    if isinstance(parsed, dict) and "messages" in parsed:
        logger.warning(
            "chat push payload recovered from raw body request_id=%s content_type=%s",
            request.headers.get("X-Request-ID", "-"),
            request.content_type,
        )
        return parsed
    return request.data
