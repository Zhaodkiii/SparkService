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
from chat_sync.ai_models.event import ChatUsageRecord
from chat_sync.ai_models.run import TERMINAL_RUN_STATUSES
from chat_sync.contracts import BlockContractError, decode_block
from chat_sync.models import ChatMessage, ChatMessageBlock, ChatThread
from chat_sync.serializers import (
    ChatPushRequestSerializer,
    ChatThreadDeleteRequestSerializer,
    ChatThreadPushRequestSerializer,
)
from common.exceptions import APIError
from common.response import success_response
from file_manager.url_utils import managed_file_download_url
from hospital_care.models import ChatMessageAttribution

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


def _to_message_push_ack(message: ChatMessage) -> dict:
    return {
        "client_message_id": str(message.client_message_id),
        "server_message_id": message.server_message_id,
        "server_updated_at": message.server_updated_at.isoformat(),
    }


def _to_block_push_ack(message: ChatMessage, block_id) -> dict:
    return {
        "client_message_id": str(message.client_message_id),
        "block_id": str(block_id),
        "server_updated_at": message.server_updated_at.isoformat(),
    }


def _to_payload(message: ChatMessage) -> dict:
    metadata = message.metadata or {}
    return {
        "thread_id": str(message.thread_id),
        "role": message.role,
        "model_name": message.model_name or None,
        "client_message_id": str(message.client_message_id),
        "server_message_id": message.server_message_id,
        "delivery_state": message.delivery_state,
        "created_at": message.created_at.isoformat(),
        "server_updated_at": message.server_updated_at.isoformat(),
        "tombstone": message.tombstone,
        "attachments": metadata.get("attachments") or [],
        # Invalid legacy rows are intentionally not migrated or reshaped. They
        # are omitted from the wire response so one stale block cannot turn the
        # whole history request into HTTP 500; all newly written blocks are
        # rejected before persistence and remain strictly iOS-compatible.
        "blocks": [item for block in message.blocks.all() if (item := _block_to_payload(block)) is not None],
        "reasoning_content": metadata.get("reasoning_content"),
        "reasoning_duration_ms": metadata.get("reasoning_duration_ms"),
        "reasoning_expanded": metadata.get("reasoning_expanded"),
        "reasoning_visibility": metadata.get("reasoning_visibility"),
        "usage_summary": _usage_summary_for_message(message),
        "turn_summary": _turn_summary_for_message(message),
        # CHAT-000056：可选 sender 快照（向后兼容）；无医院 attribution 的旧消息为 None，
        # 客户端不得把 sender 缺失的消息推断为真人医生。
        "sender": _sender_for_message(message),
    }


def _sender_for_message(message: ChatMessage) -> dict | None:
    """CHAT-000056 契约 16.3：扁平 sender 快照投影。

    事实源为 hospital_care.ChatMessageAttribution（OneToOne，related_name=hospital_attribution）。
    医生身份使用发送时快照（display_name_snapshot），医生后续改名不影响历史显示。
    """
    attribution = getattr(message, "hospital_attribution", None)
    if attribution is None:
        return None
    sender = {
        "actor_type": attribution.actor_type,
        "actor_id": str(attribution.actor_user_id or attribution.agent_id or attribution.doctor_id or ""),
        "display_name": attribution.display_name_snapshot or None,
        "avatar_url": None,
        "title": None,
        "department_name": None,
        "source": attribution.source,
    }
    doctor = attribution.doctor
    if attribution.actor_type == ChatMessageAttribution.ActorType.DOCTOR and doctor is not None:
        sender["title"] = doctor.title or None
        avatar_file = getattr(doctor, "avatar_file", None)
        if avatar_file is not None:
            sender["avatar_url"] = managed_file_download_url(avatar_file)
    agent = attribution.agent
    if attribution.actor_type == ChatMessageAttribution.ActorType.AI_AGENT and agent is not None:
        department = getattr(agent, "department", None)
        if department is not None:
            sender["department_name"] = department.name
    return sender


def _turn_summary_for_message(message: ChatMessage) -> dict | None:
    """Project a public Run summary for Activity timing. Extra JSON keys are
    ignored by iOS Codable; duration_ms is omitted when the server cannot
    compute a reliable interval.
    """
    if message.role != "assistant":
        return None
    for run in message.ai_assistant_runs.all():
        duration_ms = None
        if run.status in TERMINAL_RUN_STATUSES and run.started_at and run.finished_at:
            duration_ms = max(0, int((run.finished_at - run.started_at).total_seconds() * 1000))
        return {
            "run_id": str(run.id),
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "duration_ms": duration_ms,
            "regenerate_allowed": run.status in TERMINAL_RUN_STATUSES,
            "delete_allowed": True,
            "usage": None,
        }
    return None


def _usage_summary_for_message(message: ChatMessage) -> dict | None:
    """Project a safe, Web-facing token usage summary from the Run Usage record.

    Model names and token counts are not secrets; keys, URLs and billing amounts
    are intentionally excluded. A message without a completed Run simply omits
    the field (None), preserving iOS backward compatibility.
    """
    if message.role != "assistant":
        return None
    for run in message.ai_assistant_runs.all():
        try:
            usage = run.usage
        except ChatUsageRecord.DoesNotExist:
            continue
        return {
            "model": usage.model or None,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "reasoning_tokens": usage.reasoning_tokens,
            "model_calls": usage.model_calls,
            "tool_calls": usage.tool_calls,
        }
    return None


def _block_to_payload(block: ChatMessageBlock) -> dict | None:
    # Sync is the iOS wire contract. There is deliberately no legacy projection
    # or database migration path: invalid rows are rejected instead of being
    # silently converted into a second message model.
    stored = block.payload if isinstance(block.payload, dict) else {}
    # iOS Sync historically persisted the complete Codable block envelope in
    # this JSON column.  The wire model is still exactly one iOS block shape;
    # select its nested payload before validating and projecting it.
    if isinstance(stored.get("payload"), dict):
        raw = {
            "node_role": stored.get("node_role"),
            "payload": stored.get("payload"),
            "anchor": stored.get("anchor"),
        }
    else:
        raw = {"kind": block.kind, "node_role": block.node_role, "payload": stored, "anchor": block.anchor}
    try:
        canonical = decode_block(raw)
    except BlockContractError as exc:
        logger.warning(
            "chat sync omitted invalid block id=%s message_id=%s code=%s",
            block.id,
            block.message_id,
            exc.code,
        )
        return None
    kind, payload, node_role, anchor = canonical.kind, canonical.payload, canonical.node_role, canonical.anchor
    return {
        "id": str(block.id),
        "kind": kind,
        "status": block.status,
        "revision": block.revision,
        "order_key": block.order_key,
        "tool_call_id": block.tool_call_id or None,
        "parent_tool_call_id": block.parent_tool_call_id or None,
        "parent_block_id": str(block.parent_block_id) if block.parent_block_id else None,
        "node_role": node_role,
        "anchor": anchor,
        "payload": payload,
        "created_at": block.created_at.isoformat(),
        "updated_at": block.updated_at.isoformat(),
    }


def _block_value(raw: dict, snake: str, camel: str | None = None, default=None):
    if snake in raw:
        return raw.get(snake)
    if camel is not None and camel in raw:
        return raw.get(camel)
    return default


def _block_datetime(raw: dict, key: str, fallback: datetime) -> datetime:
    value = _block_value(raw, key, _snake_to_camel(key))
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed is not None:
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
    return fallback


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _upsert_message_blocks(*, user, thread: ChatThread, message: ChatMessage, blocks: list[dict], delete_missing: bool = True) -> None:
    incoming_ids = set()
    for raw in blocks:
        block_id = _block_value(raw, "id")
        if block_id is None:
            continue
        incoming_ids.add(block_id)
        local_revision = int(_block_value(raw, "revision", default=0) or 0)
        existing = ChatMessageBlock.objects.filter(user=user, id=block_id).first()
        if existing is not None and existing.revision > local_revision:
            continue
        incoming_status = _block_value(raw, "status", default=ChatMessageBlock.Status.READY) or ChatMessageBlock.Status.READY
        if existing is not None and existing.status == ChatMessageBlock.Status.READY and incoming_status == ChatMessageBlock.Status.PENDING:
            continue
        raw_kind = _block_value(raw, "kind")
        raw_node_role = _block_value(raw, "node_role", "nodeRole")
        raw_payload = _block_value(raw, "payload") or {}
        try:
            canonical = decode_block({"kind": raw_kind, "node_role": raw_node_role, "payload": raw_payload, "anchor": _block_value(raw, "anchor")})
        except BlockContractError as exc:
            raise APIError(
                msg=exc.code,
                code=40022,
                status_code=400,
                details={"block_id": block_id, "block_index": exc.block_index},
            ) from exc
        kind = canonical.kind
        node_role = canonical.node_role
        payload = canonical.payload

        defaults = {
            "user": user,
            "thread": thread,
            "message": message,
            "kind": kind,
            "status": incoming_status,
            "revision": local_revision,
            "order_key": _block_value(raw, "order_key", "orderKey"),
            "tool_call_id": _block_value(raw, "tool_call_id", "toolCallId") or "",
            "parent_tool_call_id": _block_value(raw, "parent_tool_call_id", "parentToolCallID") or "",
            "parent_block_id": _block_value(raw, "parent_block_id", "parentBlockID"),
            "node_role": node_role,
            "anchor": _block_value(raw, "anchor"),
            "payload": payload,
            "created_at": _block_datetime(raw, "created_at", message.created_at),
            "updated_at": _block_datetime(raw, "updated_at", message.created_at),
        }
        ChatMessageBlock.objects.update_or_create(
            user=user,
            id=block_id,
            defaults=defaults,
        )
    if delete_missing:
        ChatMessageBlock.objects.filter(user=user, message=message).exclude(id__in=incoming_ids).delete()


def _upsert_message_block_update(*, user, thread_id, client_message_id, block: dict) -> ChatMessage:
    thread = ChatThread.objects.filter(user=user, id=thread_id, is_deleted=False).first()
    if thread is None:
        raise APIError(
            msg="thread_not_found",
            code=40401,
            status_code=404,
            details={"thread_id": str(thread_id)},
        )
    message = ChatMessage.objects.filter(user=user, client_message_id=client_message_id, thread=thread).first()
    if message is None:
        raise APIError(
            msg="message_not_found",
            code=40402,
            status_code=404,
            details={"client_message_id": str(client_message_id)},
        )
    _upsert_message_blocks(user=user, thread=thread, message=message, blocks=[block], delete_missing=False)
    message.save(update_fields=["server_updated_at"])
    thread.updated_at = datetime.now(tz=timezone.utc)
    thread.save(update_fields=["updated_at", "server_updated_at"])
    return message


def _to_thread_payload(thread: ChatThread) -> dict:
    return {
        "thread_id": str(thread.id),
        "title": thread.title,
        "scenario": thread.scenario,
        "current_model_name": thread.current_model_name or None,
        "temperature": thread.temperature,
        "top_p": thread.top_p,
        "max_tokens": thread.max_tokens,
        "max_messages": thread.max_messages,
        "role_prompt": thread.role_prompt,
        "system_prompt": thread.system_prompt,
        "image_delivery_mode": thread.image_delivery_mode,
        "icon_name": thread.icon_name or None,
        "icon_color_name": thread.icon_color_name or None,
        "is_pinned": thread.is_pinned,
        "pinned_at": thread.pinned_at.isoformat() if thread.pinned_at else None,
        "patient_id": str(thread.patient_id) if thread.patient_id else None,
        "member_id": thread.member_id,
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
        block_updates_payload = serializer.validated_data["block_updates"]
        logger.info(
            "chat push payload request_id=%s user_id=%s content_type=%s body=%s",
            request_id,
            getattr(request.user, "id", "-"),
            request.content_type,
            _json_for_log(serializer.validated_data),
        )
        logger.info(
            "chat push start request_id=%s user_id=%s messages=%s block_updates=%s content_type=%s",
            request_id,
            getattr(request.user, "id", "-"),
            len(messages_payload),
            len(block_updates_payload),
            request.content_type,
        )
        if not messages_payload and not block_updates_payload:
            logger.info("chat push skipped(empty) request_id=%s", request_id)
            return success_response(
                {"accepted_messages": [], "accepted_block_updates": []},
                msg="ok",
                code=0,
            )

        accepted_messages = []
        accepted_block_updates = []
        with transaction.atomic():
            for payload in messages_payload:
                thread, _ = ChatThread.objects.get_or_create(
                    id=payload["thread_id"],
                    defaults={
                        "user": request.user,
                        "title": "New Chat",
                        "scenario": ChatThread.Scenario.CHAT,
                        "current_model_name": (payload.get("thread_current_model_name") or "").strip(),
                        "top_p": payload.get("thread_top_p") if payload.get("thread_top_p") is not None else 1.0,
                        "max_messages": payload.get("thread_max_messages") if payload.get("thread_max_messages") is not None else 20,
                        "role_prompt": payload.get("thread_system_prompt") if payload.get("thread_system_prompt") is not None else (payload.get("thread_role_prompt") or ""),
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
                thread_model_name = (payload.get("thread_current_model_name") or "").strip()
                if thread_model_name:
                    thread.current_model_name = thread_model_name
                if payload.get("thread_temperature") is not None:
                    thread.temperature = float(payload["thread_temperature"])
                if payload.get("thread_top_p") is not None:
                    thread.top_p = float(payload["thread_top_p"])
                if payload.get("thread_max_tokens") is not None:
                    thread.max_tokens = int(payload["thread_max_tokens"])
                if payload.get("thread_max_messages") is not None:
                    thread.max_messages = max(int(payload["thread_max_messages"]), 1)
                thread_system_prompt = payload.get("thread_system_prompt")
                thread_role_prompt = payload.get("thread_role_prompt")
                if thread_system_prompt is not None or thread_role_prompt is not None:
                    thread.system_prompt = thread_system_prompt if thread_system_prompt is not None else thread_role_prompt

                defaults = {
                    "thread": thread,
                    "user": request.user,
                    "role": payload["role"],
                    "model_name": (payload.get("model_name") or "").strip(),
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
                    message.model_name = (payload.get("model_name") or "").strip()
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
                            "model_name",
                            "server_message_id",
                            "delivery_state",
                            "created_at",
                            "tombstone",
                            "metadata",
                            "server_updated_at",
                        ]
                    )

                _upsert_message_blocks(
                    user=request.user,
                    thread=thread,
                    message=message,
                    blocks=payload.get("blocks") or [],
                )

                thread.updated_at = datetime.now(tz=timezone.utc)
                thread.save(
                    update_fields=[
                        "updated_at",
                        "server_updated_at",
                        "is_deleted",
                        "deleted_at",
                        "image_delivery_mode",
                        "current_model_name",
                        "temperature",
                        "top_p",
                        "max_tokens",
                        "max_messages",
                        "role_prompt",
                    ]
                )
                accepted_messages.append(_to_message_push_ack(message))

            for payload in block_updates_payload:
                block = payload["block"]
                block_id = block.get("id")
                message = _upsert_message_block_update(
                    user=request.user,
                    thread_id=payload["thread_id"],
                    client_message_id=payload["client_message_id"],
                    block=block,
                )
                if block_id is not None:
                    accepted_block_updates.append(_to_block_push_ack(message, block_id))

        logger.info(
            "chat push success request_id=%s user_id=%s accepted_messages=%s accepted_block_updates=%s",
            request_id,
            request.user.id,
            len(accepted_messages),
            len(accepted_block_updates),
        )

        return success_response(
            {
                "accepted_messages": accepted_messages,
                "accepted_block_updates": accepted_block_updates,
            },
            msg="ok",
            code=0,
        )


class ChatSyncThreadHeadView(APIView):
    """返回指定会话在服务端最新消息时间戳（仅未软删线程可查询）。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        request_id = request.headers.get("X-Request-ID", "-")
        thread_id_raw = request.query_params.get("thread_id")
        logger.info(
            "chat thread-head start request_id=%s user_id=%s thread_id=%s",
            request_id,
            getattr(request.user, "id", "-"),
            thread_id_raw,
        )
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

        logger.info(
            "chat thread-head success request_id=%s user_id=%s thread_id=%s last_server_updated_at=%s",
            request_id,
            request.user.id,
            str(thread.id),
            max_dt.isoformat() if max_dt is not None else None,
        )
        return success_response(
            {
                "thread_id": str(thread.id),
                "last_server_updated_at": max_dt.isoformat() if max_dt is not None else None,
            },
            msg="ok",
            code=0,
        )


class ChatSyncThreadPushView(APIView):
    """客户端上送会话级元数据：模型参数、图片送达方式、成员档案绑定等。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_id = request.headers.get("X-Request-ID", "-")
        serializer = ChatThreadPushRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        threads_payload = serializer.validated_data["threads"]
        logger.info(
            "chat thread-push start request_id=%s user_id=%s threads=%s body=%s",
            request_id,
            getattr(request.user, "id", "-"),
            len(threads_payload),
            _json_for_log(serializer.validated_data),
        )
        if not threads_payload:
            logger.info("chat thread-push skipped(empty) request_id=%s", request_id)
            return success_response({"threads": []}, msg="ok", code=0)

        result = []
        with transaction.atomic():
            for payload in threads_payload:
                thread, _ = ChatThread.objects.get_or_create(
                    id=payload["thread_id"],
                    defaults={
                        "user": request.user,
                        "title": payload.get("title") or "New Chat",
                        "scenario": payload.get("scenario") or ChatThread.Scenario.CHAT,
                    },
                )
                if thread.user_id != request.user.id:
                    raise APIError(
                        msg="thread_id_conflict",
                        code=40901,
                        status_code=409,
                        details={"thread_id": str(payload["thread_id"])},
                    )

                thread.title = payload.get("title") or thread.title or "New Chat"
                thread.scenario = payload.get("scenario") or ChatThread.Scenario.CHAT
                thread.patient_id = payload.get("patient_id")
                thread.member_id = payload.get("member_id")
                thread.is_deleted = payload.get("is_deleted", False)
                thread.deleted_at = payload.get("deleted_at")
                thread.image_delivery_mode = payload.get("image_delivery_mode") or None
                thread.icon_name = (payload.get("icon_name") or "").strip()
                thread.icon_color_name = (payload.get("icon_color_name") or "").strip()
                if payload.get("is_pinned") is not None:
                    thread.is_pinned = bool(payload["is_pinned"])
                    thread.pinned_at = payload.get("pinned_at") if thread.is_pinned else None
                thread.current_model_name = (payload.get("current_model_name") or "").strip()
                if payload.get("temperature") is not None:
                    thread.temperature = float(payload["temperature"])
                if payload.get("top_p") is not None:
                    thread.top_p = float(payload["top_p"])
                if payload.get("max_tokens") is not None:
                    thread.max_tokens = int(payload["max_tokens"])
                if payload.get("max_messages") is not None:
                    thread.max_messages = max(int(payload["max_messages"]), 1)
                system_prompt = payload.get("system_prompt")
                role_prompt = payload.get("role_prompt")
                if system_prompt is not None or role_prompt is not None:
                    thread.system_prompt = system_prompt if system_prompt is not None else role_prompt
                thread.updated_at = datetime.now(tz=timezone.utc)
                thread.save(
                    update_fields=[
                        "title",
                        "scenario",
                        "patient_id",
                        "member_id",
                        "is_deleted",
                        "deleted_at",
                        "image_delivery_mode",
                        "icon_name",
                        "icon_color_name",
                        "is_pinned",
                        "pinned_at",
                        "current_model_name",
                        "temperature",
                        "top_p",
                        "max_tokens",
                        "max_messages",
                        "role_prompt",
                        "updated_at",
                        "server_updated_at",
                    ]
                )
                result.append(_to_thread_payload(thread))

        logger.info(
            "chat thread-push success request_id=%s user_id=%s accepted=%s",
            request_id,
            request.user.id,
            len(result),
        )
        return success_response({"threads": result}, msg="ok", code=0)


class ChatSyncThreadPullView(APIView):
    """按线程维度拉增量，用于最小带宽同步会话列表与软删除状态。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        request_id = request.headers.get("X-Request-ID", "-")
        cursor = request.query_params.get("cursor")
        cursor_dt, cursor_tie = _decode_cursor(cursor)
        limit = _normalize_limit(request.query_params.get("limit"), default=100, max_value=200)
        logger.info(
            "chat thread-pull start request_id=%s user_id=%s cursor=%s limit=%s",
            request_id,
            getattr(request.user, "id", "-"),
            cursor,
            limit,
        )

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
            request_id,
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
        request_id = request.headers.get("X-Request-ID", "-")
        serializer = ChatThreadDeleteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        requested_ids = serializer.validated_data["thread_ids"]
        logger.info(
            "chat thread-delete payload request_id=%s user_id=%s body=%s",
            request_id,
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
            request_id,
            request.user.id,
            len(requested_ids),
            len(changed_ids),
        )
        return success_response({"thread_ids": [str(i) for i in changed_ids]}, msg="ok", code=0)


class ChatSyncPullView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        request_id = request.headers.get("X-Request-ID", "-")
        cursor = request.query_params.get("cursor")
        cursor_dt, cursor_tie = _decode_cursor(cursor)
        limit = _normalize_limit(request.query_params.get("limit"), default=200, max_value=200)
        thread_id_raw = request.query_params.get("thread_id")
        logger.info(
            "chat pull start request_id=%s user_id=%s cursor=%s limit=%s thread_id=%s",
            request_id,
            getattr(request.user, "id", "-"),
            cursor,
            limit,
            thread_id_raw,
        )

        queryset = ChatMessage.objects.filter(user=request.user, thread__is_deleted=False).prefetch_related("blocks", "ai_assistant_runs__usage")
        # CHAT-000056：sender 投影预取 attribution 及医生/智能体关系，避免逐消息 N+1。
        queryset = queryset.select_related(
            "hospital_attribution__doctor__avatar_file",
            "hospital_attribution__agent__department",
        )

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
            request_id,
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
