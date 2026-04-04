import uuid
import json
import logging
from datetime import datetime, timezone

from django.db import transaction
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from chat_sync.models import ChatMessage, ChatThread
from chat_sync.serializers import ChatPushRequestSerializer
from chat_sync.events import ChatSyncNotifier
from common.exceptions import APIError
from common.response import success_response

logger = logging.getLogger("chat_sync.sync")


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


def _to_payload(message: ChatMessage) -> dict:
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
        message_ids = []
        cursor_dt = None
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

                server_message_id = payload.get("server_message_id")
                if server_message_id is None or server_message_id == "":
                    server_message_id = str(uuid.uuid4())

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
                    message.save(update_fields=[
                        "thread",
                        "role",
                        "kind",
                        "content",
                        "server_message_id",
                        "delivery_state",
                        "created_at",
                        "tombstone",
                        "server_updated_at",
                    ])

                thread.updated_at = datetime.now(tz=timezone.utc)
                thread.save(update_fields=["updated_at", "server_updated_at"])
                result.append(_to_payload(message))
                message_ids.append(str(message.client_message_id))
                if cursor_dt is None or message.server_updated_at > cursor_dt:
                    cursor_dt = message.server_updated_at

        if cursor_dt is not None and message_ids:
            ChatSyncNotifier.notify_user_sync(
                user_id=request.user.id,
                cursor=cursor_dt.isoformat(),
                message_ids=message_ids,
            )
        logger.info(
            "chat push success request_id=%s user_id=%s accepted=%s",
            request_id,
            request.user.id,
            len(result),
        )

        return success_response({"messages": result}, msg="ok", code=0)


class ChatSyncPullView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cursor = request.query_params.get("cursor")
        cursor_dt = _normalize_cursor(cursor)

        queryset = ChatMessage.objects.filter(user=request.user)
        if cursor_dt is not None:
            queryset = queryset.filter(server_updated_at__gt=cursor_dt)

        messages = list(queryset.order_by("server_updated_at", "id")[:200])
        payload = [_to_payload(item) for item in messages]
        next_cursor = messages[-1].server_updated_at.isoformat() if messages else cursor
        logger.info(
            "chat pull success request_id=%s user_id=%s input_cursor=%s next_cursor=%s count=%s",
            request.headers.get("X-Request-ID", "-"),
            request.user.id,
            cursor,
            next_cursor,
            len(payload),
        )
        return success_response({"cursor": next_cursor, "messages": payload}, msg="ok", code=0)


def _normalize_delivery_state(state: str) -> str:
    if state in (ChatMessage.DeliveryState.PENDING, ChatMessage.DeliveryState.SENDING):
        return ChatMessage.DeliveryState.SENT
    if state in ChatMessage.DeliveryState.values:
        return state
    return ChatMessage.DeliveryState.SENT


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
