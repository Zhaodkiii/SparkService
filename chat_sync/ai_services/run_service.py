from __future__ import annotations

import hashlib
import json
import logging
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from chat_sync.ai_models import (
    ChatEventOutbox,
    ChatRun,
    ChatRunEvent,
    ChatThreadRunLock,
    RunStatus,
)
from chat_sync.ai_models.run import assert_run_transition
from chat_sync.ai_runtime.capabilities import CapabilityUnavailable, build_capability_registry
from chat_sync.ai_services.image_support import validate_image_attachments
from chat_sync.contracts import BlockContractError, NODE_ROLE_TIMELINE, decode_block
from chat_sync.models import ChatMessage, ChatMessageBlock, ChatThread
from common.exceptions import APIError

logger = logging.getLogger("chat_sync.ai.run_service")


TERMINAL_EVENT_TYPES = {
    RunStatus.COMPLETED: "run.completed",
    RunStatus.FAILED: "run.failed",
    RunStatus.CANCELLED: "run.cancelled",
    RunStatus.INTERRUPTED: "run.interrupted",
}


@dataclass(frozen=True)
class RunCommandResult:
    run: ChatRun
    replayed: bool = False


class RunService:
    """The only P1 write orchestration entry point for ChatRun.

    Provider calls, context construction, tool execution and Channels relay are
    intentionally absent. P1 owns durable state, idempotency and terminal
    convergence; later phases replace the executor behind this service.
    """

    @staticmethod
    def _api_error(msg: str, code: int, status_code: int, details: dict[str, Any] | None = None) -> APIError:
        return APIError(msg=msg, code=code, status_code=status_code, details=details)

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    @staticmethod
    def _to_json_value(value: Any) -> Any:
        if value is None:
            return None
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))

    @classmethod
    def _request_snapshot(cls, payload: dict[str, Any], operation: str = "create", target_run_id: str | None = None) -> dict[str, Any]:
        client = payload.get("client") or {}
        snapshot = {
            "schema_version": 1,
            "operation": operation,
            "content": payload.get("content") or "",
            "capability": payload.get("capability") or "chat",
            "client_message_id": str(payload.get("client_message_id")),
            "preferences_revision": payload.get("preferences_revision"),
            "context_parent_message_id": payload.get("context_parent_message_id"),
            "references": payload.get("references") or [],
            "attachments": payload.get("attachments") or [],
            "capability_config": payload.get("capability_config") or {},
            "input_message": cls._to_json_value(payload.get("input_message")),
            "run_options": cls._to_json_value(payload.get("run_options")),
            "client": {
                "platform": str(client.get("platform") or "")[:32],
                "version": str(client.get("version") or "")[:64],
                "device_id": str(client.get("device_id") or "")[:128],
                "client_tools": [
                    {"name": str(item.get("name") or "")[:128], "version": str(item.get("version") or "")[:64]}
                    for item in (client.get("client_tools") or [])[:32]
                    if isinstance(item, dict) and item.get("name")
                ],
            },
        }
        if target_run_id:
            snapshot["target_run_id"] = str(target_run_id)
        return snapshot

    @classmethod
    def _create_input_message_blocks(
        cls,
        user,
        thread: ChatThread,
        message: ChatMessage,
        input_message: dict[str, Any],
        now,
    ) -> None:
        """Persist the canonical input_message blocks (Create Run v2)."""
        message.created_at = cls._parse_datetime(input_message.get("created_at")) or now
        message.save(update_fields=["created_at"])
        for index, raw_block in enumerate(input_message.get("blocks") or []):
            raw_block = raw_block or {}
            try:
                canonical = decode_block(
                    {
                        "kind": raw_block.get("kind"),
                        "node_role": raw_block.get("node_role"),
                        "payload": raw_block.get("payload") or {},
                        "anchor": raw_block.get("anchor"),
                    },
                    block_index=index,
                )
            except BlockContractError as exc:
                raise cls._api_error(
                    exc.code,
                    40022,
                    400,
                    {"field": f"input_message.blocks[{index}]", "error": exc.code},
                ) from exc
            ChatMessageBlock.objects.create(
                user=user,
                thread=thread,
                message=message,
                id=raw_block.get("id") or uuid.uuid4(),
                kind=canonical.kind,
                status=raw_block.get("status") or ChatMessageBlock.Status.READY,
                revision=int(raw_block.get("revision") or 0),
                order_key=raw_block.get("order_key") if raw_block.get("order_key") is not None else 1000 + index,
                tool_call_id=raw_block.get("tool_call_id") or "",
                parent_tool_call_id=raw_block.get("parent_tool_call_id") or "",
                parent_block_id=raw_block.get("parent_block_id"),
                node_role=canonical.node_role,
                anchor=canonical.anchor,
                payload=canonical.payload,
                created_at=now,
                updated_at=now,
            )

    @staticmethod
    def _parse_datetime(value: Any) -> Any:
        if not value:
            return None
        try:
            from django.utils.dateparse import parse_datetime

            parsed = parse_datetime(str(value))
            return parsed if parsed else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _freeze_preferences(cls, thread: ChatThread, requested_revision: int | None) -> tuple[dict[str, Any], int, ChatMessage | None]:
        from chat_sync.ai_models import ChatThreadPreferences

        prefs, _ = ChatThreadPreferences.objects.select_for_update().get_or_create(thread=thread)
        if requested_revision is not None and int(requested_revision) != prefs.revision:
            raise cls._api_error("chat_preferences_revision_conflict", 40993, 409, {"revision": prefs.revision})
        data = {key: getattr(prefs, key) for key in ("capability", "enabled_tools", "knowledge_bases", "subagent", "persona", "llm_selection", "language", "voice_preferences")}
        from chat_sync.ai_knowledge.services.preference_validation import validate_knowledge_base_ids

        validated = validate_knowledge_base_ids(thread.user, data.get("knowledge_bases") or [])
        data["knowledge_bases"] = validated["knowledge_bases"]
        return data, prefs.revision, prefs.active_head_message

    @classmethod
    def _request_hash(cls, snapshot: dict[str, Any]) -> str:
        return hashlib.sha256(cls._canonical_json(snapshot).encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_idempotency_key(value: str | None) -> str:
        key = (value or "").strip()
        if not key or len(key) > 128 or any(ord(char) < 32 for char in key):
            raise APIError("chat_run_request_invalid", code=40091, status_code=400, details={"field": "Idempotency-Key"})
        return key

    @staticmethod
    def _ensure_enabled() -> None:
        if not getattr(settings, "CHAT_AI_SERVER_RUNS_ENABLED", False):
            raise APIError("chat_server_runs_disabled", code=50392, status_code=503, details={"retryable": False})

    @staticmethod
    def _channel_group(run: ChatRun) -> str:
        return f"chat_run_{run.id.hex}"

    @classmethod
    def serialize_run(cls, run: ChatRun) -> dict[str, Any]:
        error = None
        if run.error_code:
            error = {
                "code": run.error_code,
                "message": run.error_message or run.error_code,
                "retryable": run.retryable,
            }
        return {
            "id": str(run.id),
            "thread_id": str(run.thread_id),
            "status": run.status,
            "capability": run.capability,
            "capability_version": run.capability_version,
            "capability_manifest_hash": (run.request_snapshot or {}).get("capability_manifest_hash", ""),
            "user_message_id": run.user_message_id,
            "assistant_message_id": run.assistant_message_id,
            "last_sequence": run.last_sequence,
            "error": error,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "finish_reason": run.finish_reason,
            "provider_request_id": run.provider_request_id,
        }

    @classmethod
    def serialize_event(cls, event: ChatRunEvent) -> dict[str, Any]:
        return {
            "type": event.type,
            "event_id": str(event.event_id),
            "payload_version": event.payload_version,
            "run_id": str(event.run_id),
            "thread_id": str(event.run.thread_id),
            "sequence": event.sequence,
            "timestamp": event.created_at.isoformat() if event.created_at else None,
            "payload": event.payload or {},
        }

    @classmethod
    def _append_event_locked(
        cls,
        *,
        run: ChatRun,
        event_type: str,
        payload: dict[str, Any] | None = None,
        terminal_marker: str | None = None,
    ) -> ChatRunEvent:
        sequence = int(run.last_sequence) + 1
        event = ChatRunEvent.objects.create(
            run=run,
            sequence=sequence,
            type=event_type,
            payload_version=1,
            payload=payload or {},
            terminal_marker=terminal_marker,
        )
        run.last_sequence = sequence
        run.save(update_fields=["last_sequence", "updated_at"])
        envelope = cls.serialize_event(event)
        ChatEventOutbox.objects.create(
            event=event,
            channel_group=cls._channel_group(run),
            payload=envelope,
            status=ChatEventOutbox.Status.PENDING,
        )
        if getattr(settings, "CHAT_AI_OUTBOX_IMMEDIATE_RELAY", True):
            transaction.on_commit(cls._enqueue_outbox_relay, robust=True)
        cls._log_event_commit_timing(run=run, sequence=sequence, event_type=event_type)
        return event

    @staticmethod
    def _log_event_commit_timing(*, run: ChatRun, sequence: int, event_type: str) -> None:
        """W0 observability: elapsed time from run start to durable event commit.

        Cheap structured log line (no new metrics infra) so a run's end-to-end
        waterfall (Provider Chunk -> Event Commit -> Outbox Publish -> Web
        Receive -> UI Paint) can be reconstructed offline for P95 analysis.
        """
        reference = run.started_at or run.created_at
        elapsed_ms = int((timezone.now() - reference).total_seconds() * 1000) if reference else None
        logger.info(
            "chat_event.committed run_id=%s sequence=%s event_type=%s elapsed_ms=%s",
            run.id,
            sequence,
            event_type,
            elapsed_ms,
        )

    @staticmethod
    def _enqueue_outbox_relay() -> None:
        try:
            from chat_sync.ai_tasks.outbox_tasks import relay_chat_event_outbox

            relay_chat_event_outbox.delay(limit=100)
        except Exception:  # pragma: no cover - broker failures use beat fallback
            logger.exception("chat_event_outbox.enqueue_failed")

    @classmethod
    def _get_thread_and_lock_locked(cls, *, user_id: int, thread_id: uuid.UUID) -> tuple[ChatThread, ChatThreadRunLock]:
        thread = (
            ChatThread.objects.select_for_update()
            .filter(id=thread_id, user_id=user_id, is_deleted=False)
            .first()
        )
        if thread is None:
            raise cls._api_error("chat_thread_not_found", 40491, 404)
        ChatThreadRunLock.objects.get_or_create(thread=thread, defaults={"generation": 0})
        lock = ChatThreadRunLock.objects.select_for_update().get(thread=thread)
        return thread, lock

    @classmethod
    def _get_run_locked(cls, *, user_id: int, run_id: uuid.UUID) -> ChatRun:
        run = ChatRun.objects.select_for_update().filter(id=run_id, user_id=user_id).first()
        if run is None:
            raise cls._api_error("chat_run_not_found", 40491, 404)
        return run

    @classmethod
    def create_run(
        cls,
        *,
        user,
        thread_id: uuid.UUID,
        payload: dict[str, Any],
        idempotency_key: str,
        request_id: str = "",
        enforce_enabled: bool = True,
    ) -> RunCommandResult:
        if enforce_enabled:
            cls._ensure_enabled()
        key = cls._validate_idempotency_key(idempotency_key)
        snapshot = cls._request_snapshot(payload)
        try:
            capability = build_capability_registry().require(snapshot["capability"])
        except CapabilityUnavailable as exc:
            raise cls._api_error("chat_capability_unavailable", 40097, 400, {"capability": snapshot["capability"], "reason": exc.reason}) from exc
        snapshot["capability_version"] = capability.version
        snapshot["capability_manifest_hash"] = capability.manifest_hash
        snapshot["capability_config"] = payload.get("capability_config") or {}
        request_hash = cls._request_hash(snapshot)

        with transaction.atomic():
            existing = (
                ChatRun.objects.select_for_update()
                .filter(user_id=user.id, idempotency_key=key)
                .first()
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise cls._api_error("chat_idempotency_conflict", 40992, 409)
                return RunCommandResult(existing, replayed=True)

            thread, lock = cls._get_thread_and_lock_locked(user_id=user.id, thread_id=thread_id)
            frozen_preferences, frozen_revision, context_parent = cls._freeze_preferences(thread, payload.get("preferences_revision"))
            requested_parent_id = payload.get("context_parent_message_id")
            if requested_parent_id is not None:
                requested_parent = ChatMessage.objects.filter(
                    id=requested_parent_id,
                    thread=thread,
                    user=user,
                    tombstone=False,
                    role__in=[ChatMessage.Role.USER, ChatMessage.Role.ASSISTANT],
                ).first()
                if requested_parent is None:
                    raise cls._api_error("chat_context_reference_invalid", 40094, 400, {"field": "context_parent_message_id"})
                context_parent = requested_parent
            snapshot["preferences_revision"] = frozen_revision
            snapshot["preferences"] = frozen_preferences
            snapshot["context_parent_message_id"] = context_parent.id if context_parent else None

            now = timezone.now()
            client_message_id = payload["client_message_id"]
            input_message = payload["input_message"]
            if str(input_message.get("thread_id")) != str(thread.id):
                raise cls._api_error("chat_input_thread_mismatch", 40091, 400, {"field": "input_message.thread_id"})

            # client_message_id 幂等：同一用户重复提交同一消息 ID 时复用该消息
            # 最近一次 Run 作为 replayed 结果，避免 (user, client_message_id)
            # 唯一约束抛出裸 IntegrityError。
            existing_message = ChatMessage.objects.filter(user=user, client_message_id=client_message_id).first()
            if existing_message is not None:
                if existing_message.thread_id != thread.id:
                    raise cls._api_error("chat_idempotency_conflict", 40992, 409)
                last_run = (
                    ChatRun.objects.filter(user_id=user.id, user_message=existing_message)
                    .order_by("-created_at")
                    .first()
                )
                if last_run is None:
                    # 消息已存在但尚无 Run（例如旧 sync 推送链路写入）：明确报
                    # 处理中/冲突，而非唯一约束 500。40993/40994 已被占用，故用 40980。
                    raise cls._api_error("chat_run_idempotency_pending", 40980, 409, {"client_message_id": str(client_message_id)})
                if last_run.request_hash != request_hash:
                    raise cls._api_error("chat_idempotency_conflict", 40992, 409)
                return RunCommandResult(last_run, replayed=True)

            if lock.active_run_id:
                active = ChatRun.objects.filter(id=lock.active_run_id).first()
                if active is not None and not active.is_terminal:
                    raise cls._api_error("chat_run_already_active", 40991, 409, {"run_id": str(active.id)})
                lock.active_run = None
                lock.save(update_fields=["active_run", "updated_at"])

            # 图片附件校验（CHAT-WEB-029）：无 type=image 附件时内部直接返回。
            validate_image_attachments(user=user, thread=thread, payload=payload)

            user_message = ChatMessage.objects.create(
                user=user,
                thread=thread,
                role=ChatMessage.Role.USER,
                client_message_id=client_message_id,
                server_message_id=str(uuid.uuid4()),
                delivery_state=ChatMessage.DeliveryState.SENT,
                created_at=now,
                # attachments 写入消息 metadata，使消息 wire 能原样返回附件。
                metadata={"attachments": snapshot["attachments"]},
            )
            cls._create_input_message_blocks(user, thread, user_message, input_message, now)
            assistant_message = ChatMessage.objects.create(
                user=user,
                thread=thread,
                role=ChatMessage.Role.ASSISTANT,
                client_message_id=uuid.uuid4(),
                server_message_id=str(uuid.uuid4()),
                delivery_state=ChatMessage.DeliveryState.PENDING,
                # Keep the assistant placeholder strictly after the accepted
                # user message. This preserves a deterministic timeline even
                # when clients truncate timestamps to milliseconds/seconds.
                created_at=now + timedelta(microseconds=1),
            )
            run = ChatRun.objects.create(
                user=user,
                thread=thread,
                user_message=user_message,
                assistant_message=assistant_message,
                status=RunStatus.QUEUED,
                capability=snapshot["capability"],
                capability_version=capability.version,
                idempotency_key=key,
                request_hash=request_hash,
                request_snapshot=snapshot,
                context_parent_message=context_parent,
                max_attempts=1,
            )
            lock.generation += 1
            lock.active_run = run
            lock.save(update_fields=["generation", "active_run", "updated_at"])
            cls._append_event_locked(
                run=run,
                event_type="run.queued",
                payload={"status": RunStatus.QUEUED, "queue": "chat.ai"},
            )
            thread.updated_at = now
            thread.server_updated_at = now
            thread.save(update_fields=["updated_at", "server_updated_at"])
            generation = lock.generation
            run_id = run.id
            transaction.on_commit(
                lambda: cls._enqueue_run(run_id, generation, request_id),
                robust=True,
            )
            logger.info(
                "chat_run.create.accepted run_id=%s thread_id=%s user_id=%s generation=%s",
                run.id,
                thread.id,
                user.id,
                generation,
            )
            return RunCommandResult(run, replayed=False)

    @classmethod
    def _enqueue_mock(cls, run_id: uuid.UUID, generation: int, request_id: str) -> None:
        if getattr(settings, "CHAT_AI_RUN_EXECUTOR", "disabled") != "mock":
            return
        try:
            from chat_sync.ai_tasks.run_tasks import run_chat

            run_chat.delay(str(run_id), expected_generation=generation, request_id=request_id)
        except Exception:  # pragma: no cover - broker failures are integration-only
            logger.exception("chat_run.enqueue.failed run_id=%s", run_id)

    @classmethod
    def _enqueue_run(cls, run_id: uuid.UUID, generation: int, request_id: str) -> None:
        if getattr(settings, "CHAT_AI_RUN_EXECUTOR", "disabled") not in {"mock", "provider"}:
            return
        try:
            from chat_sync.ai_tasks.run_tasks import run_chat
            run_chat.delay(str(run_id), expected_generation=generation, request_id=request_id)
        except Exception:
            logger.exception("chat_run.enqueue.failed run_id=%s", run_id)

    @classmethod
    def get_run(cls, *, user_id: int, run_id: uuid.UUID) -> ChatRun:
        run = ChatRun.objects.filter(id=run_id, user_id=user_id).first()
        if run is None:
            raise cls._api_error("chat_run_not_found", 40491, 404)
        return run

    @classmethod
    def list_events(cls, *, user_id: int, run_id: uuid.UUID, after_sequence: int, limit: int) -> list[ChatRunEvent]:
        if after_sequence < 0 or limit < 1 or limit > 200:
            raise cls._api_error("chat_run_request_invalid", 40091, 400, {"field": "cursor"})
        run = cls.get_run(user_id=user_id, run_id=run_id)
        return list(run.events.filter(sequence__gt=after_sequence).order_by("sequence", "id")[:limit])

    @classmethod
    def request_cancel(cls, *, user_id: int, run_id: uuid.UUID, request_id: str = "") -> ChatRun:
        with transaction.atomic():
            run0 = ChatRun.objects.filter(id=run_id, user_id=user_id).first()
            if run0 is None:
                raise cls._api_error("chat_run_not_found", 40491, 404)
            thread, lock = cls._get_thread_and_lock_locked(user_id=user_id, thread_id=run0.thread_id)
            run = ChatRun.objects.select_for_update().get(pk=run_id)
            if run.is_terminal:
                return run
            if run.status == RunStatus.QUEUED:
                cls._finalize_locked(run=run, lock=lock, status=RunStatus.CANCELLED)
                return run
            if run.status in {RunStatus.WAITING_FOR_USER_INPUT, RunStatus.WAITING_FOR_CLIENT_TOOL}:
                from chat_sync.ai_services.pending_interaction_service import PendingInteractionService

                PendingInteractionService.cancel_for_run(user_id=user_id, run_id=run.id)
                run.refresh_from_db()
                cls._finalize_locked(run=run, lock=lock, status=RunStatus.CANCELLED)
                return run
            if run.cancel_requested_at is None:
                run.cancel_requested_at = timezone.now()
                run.save(update_fields=["cancel_requested_at", "updated_at"])
                cls._append_event_locked(
                    run=run,
                    event_type="run.cancel_requested",
                    payload={"requested_at": run.cancel_requested_at.isoformat()},
                )
                logger.info("chat_run.cancel.requested run_id=%s request_id=%s", run.id, request_id)
            return run

    @classmethod
    def _finalize_locked(
        cls,
        *,
        run: ChatRun,
        lock: ChatThreadRunLock,
        status: str,
        error_code: str = "",
        error_message: str = "",
        retryable: bool = False,
    ) -> ChatRun:
        if run.is_terminal:
            return run
        assert_run_transition(run.status, status)
        event_type = TERMINAL_EVENT_TYPES[status]
        cls._append_event_locked(
            run=run,
            event_type=event_type,
            payload={
                "status": status,
                **({"error": {"code": error_code, "message": error_message, "retryable": retryable}} if error_code else {}),
            },
            terminal_marker="terminal",
        )
        run.status = status
        run.finished_at = timezone.now()
        run.error_code = error_code
        run.error_message = error_message[:2000]
        run.retryable = retryable
        run.lease_owner = ""
        run.lease_token = None
        run.lease_expires_at = None
        run.assistant_message.delivery_state = (
            ChatMessage.DeliveryState.SENT
            if status == RunStatus.COMPLETED
            else ChatMessage.DeliveryState.FAILED
        )
        run.assistant_message.save(update_fields=["delivery_state", "server_updated_at"])
        cls._append_event_locked(
            run=run,
            event_type="run.done",
            payload={"terminal_status": status},
            terminal_marker="done",
        )
        run.save(
            update_fields=[
                "status",
                "finished_at",
                "error_code",
                "error_message",
                "retryable",
                "lease_owner",
                "lease_token",
                "lease_expires_at",
                "updated_at",
            ]
        )
        if status == RunStatus.COMPLETED:
            from chat_sync.ai_models import ChatThreadPreferences

            prefs = ChatThreadPreferences.objects.select_for_update().filter(thread_id=run.thread_id).first()
            if prefs is not None and (prefs.active_head_message_id in {None, run.context_parent_message_id} or run.regenerated_from_run_id):
                prefs.active_head_message = run.assistant_message
                prefs.save(update_fields=["active_head_message", "updated_at"])
        if lock.active_run_id == run.id:
            lock.active_run = None
            lock.save(update_fields=["active_run", "updated_at"])
        return run

    @classmethod
    def claim_mock(cls, *, run_id: uuid.UUID, expected_generation: int | None = None) -> ChatRun | None:
        with transaction.atomic():
            run0 = ChatRun.objects.filter(id=run_id).first()
            if run0 is None:
                return None
            thread, lock = cls._get_thread_and_lock_locked(user_id=run0.user_id, thread_id=run0.thread_id)
            run = ChatRun.objects.select_for_update().get(pk=run_id)
            if run.is_terminal or run.status != RunStatus.QUEUED:
                return None
            if lock.active_run_id != run.id or (expected_generation is not None and lock.generation != expected_generation):
                logger.warning("chat_run.lock.stale_generation run_id=%s", run.id)
                return None
            run.status = RunStatus.RUNNING
            now = timezone.now()
            run.started_at = now
            run.attempt_count += 1
            run.lease_owner = f"{socket.gethostname()}:{uuid.uuid4().hex[:12]}"
            run.lease_token = uuid.uuid4()
            run.lease_expires_at = now + timedelta(seconds=max(5, int(getattr(settings, "CHAT_AI_LEASE_TTL_SECONDS", 45))))
            run.save(update_fields=["status", "started_at", "attempt_count", "lease_owner", "lease_token", "lease_expires_at", "updated_at"])
            run.assistant_message.delivery_state = ChatMessage.DeliveryState.SENDING
            run.assistant_message.save(update_fields=["delivery_state", "server_updated_at"])
            cls._append_event_locked(
                run=run,
                event_type="run.started",
                payload={"status": RunStatus.RUNNING, "attempt": run.attempt_count},
            )
            cls._append_event_locked(
                run=run,
                event_type="assistant.status",
                payload={"state": "thinking", "status": "thinking"},
            )
            return run

    claim_for_execution = claim_mock

    @classmethod
    def heartbeat_execution(cls, *, run_id: uuid.UUID, lease_token: uuid.UUID) -> str:
        """Renew a live worker lease and return running/cancelled/lost."""
        with transaction.atomic():
            run = ChatRun.objects.select_for_update().filter(pk=run_id).first()
            if run is None or run.is_terminal or run.status != RunStatus.RUNNING or run.lease_token != lease_token:
                return "lost"
            if run.cancel_requested_at is not None:
                return "cancelled"
            run.lease_expires_at = timezone.now() + timedelta(
                seconds=max(5, int(getattr(settings, "CHAT_AI_LEASE_TTL_SECONDS", 45)))
            )
            run.save(update_fields=["lease_expires_at", "updated_at"])
            return "running"

    @classmethod
    def finalize_mock(cls, *, run_id: uuid.UUID, status: str, error_code: str = "", error_message: str = "") -> ChatRun | None:
        with transaction.atomic():
            run0 = ChatRun.objects.filter(id=run_id).first()
            if run0 is None:
                return None
            thread, lock = cls._get_thread_and_lock_locked(user_id=run0.user_id, thread_id=run0.thread_id)
            run = ChatRun.objects.select_for_update().get(pk=run_id)
            if run.is_terminal:
                return run
            if run.cancel_requested_at is not None:
                status = RunStatus.CANCELLED
                error_code = ""
                error_message = ""
            cls._finalize_locked(
                run=run,
                lock=lock,
                status=status,
                error_code=error_code,
                error_message=error_message,
            )
            return run

    @classmethod
    def regenerate(
        cls,
        *,
        user,
        run_id: uuid.UUID,
        idempotency_key: str,
        request_id: str = "",
        enforce_enabled: bool = True,
    ) -> RunCommandResult:
        if enforce_enabled:
            cls._ensure_enabled()
        key = cls._validate_idempotency_key(idempotency_key)
        with transaction.atomic():
            source = ChatRun.objects.filter(id=run_id, user_id=user.id).first()
            if source is None:
                raise cls._api_error("chat_run_not_found", 40491, 404)
            snapshot = dict(source.request_snapshot or {})
            snapshot["operation"] = "regenerate"
            snapshot["target_run_id"] = str(source.id)
            request_hash = cls._request_hash(snapshot)
            existing = ChatRun.objects.select_for_update().filter(user_id=user.id, idempotency_key=key).first()
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise cls._api_error("chat_idempotency_conflict", 40992, 409)
                return RunCommandResult(existing, replayed=True)
            thread, lock = cls._get_thread_and_lock_locked(user_id=user.id, thread_id=source.thread_id)
            source = ChatRun.objects.select_for_update().get(pk=source.pk)
            if not source.is_terminal:
                raise cls._api_error("chat_run_already_active", 40991, 409)
            if lock.active_run_id:
                active = ChatRun.objects.filter(id=lock.active_run_id).first()
                if active is not None and not active.is_terminal:
                    raise cls._api_error("chat_run_already_active", 40991, 409, {"run_id": str(active.id)})
                lock.active_run = None
                lock.save(update_fields=["active_run", "updated_at"])
            now = timezone.now()
            assistant_message = ChatMessage.objects.create(
                user=user,
                thread=thread,
                role=ChatMessage.Role.ASSISTANT,
                client_message_id=uuid.uuid4(),
                server_message_id=str(uuid.uuid4()),
                delivery_state=ChatMessage.DeliveryState.PENDING,
                # Regeneration reuses the original user message; retain the
                # same strict user -> assistant ordering invariant.
                created_at=max(now, source.user_message.created_at + timedelta(microseconds=1)),
            )
            run = ChatRun.objects.create(
                user=user,
                thread=thread,
                user_message=source.user_message,
                assistant_message=assistant_message,
                status=RunStatus.QUEUED,
                capability=source.capability,
                capability_version=source.capability_version,
                idempotency_key=key,
                request_hash=request_hash,
                request_snapshot=snapshot,
                context_parent_message=source.context_parent_message,
                regenerated_from_run=source,
                regenerated_from_message=source.assistant_message,
                max_attempts=1,
            )
            lock.generation += 1
            lock.active_run = run
            lock.save(update_fields=["generation", "active_run", "updated_at"])
            cls._append_event_locked(run=run, event_type="run.queued", payload={"status": RunStatus.QUEUED, "queue": "chat.ai"})
            thread.updated_at = now
            thread.server_updated_at = now
            thread.save(update_fields=["updated_at", "server_updated_at"])
            generation = lock.generation
            transaction.on_commit(lambda: cls._enqueue_run(run.id, generation, request_id), robust=True)
            return RunCommandResult(run, replayed=False)

