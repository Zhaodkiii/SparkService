from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import transaction
from django.utils import timezone

from chat_sync.ai_models import ChatRun, ChatThreadRunLock, ChatUsageRecord, RunStatus
from chat_sync.ai_services.run_service import RunService
from chat_sync.contracts import KIND_DEEP_THOUGHT, KIND_TEXT, NODE_ROLE_TIMELINE, deep_thought_payload, payload_text, text_payload
from chat_sync.models import ChatMessageBlock


class RunLeaseLost(RuntimeError):
    pass


class RunExecutionCancelled(RuntimeError):
    pass


def _usage_value(usage: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, (int, float)) and value >= 0:
            return int(value)
    return 0


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class StreamWriter:
    """Project provider output into durable Blocks and replayable v1 events."""

    @staticmethod
    def _assert_execution(run: ChatRun, lease_token=None) -> None:
        if run.is_terminal:
            raise RunLeaseLost("run is already terminal")
        if lease_token is not None and run.lease_token != lease_token:
            raise RunLeaseLost("run worker lease was replaced")
        if run.cancel_requested_at is not None:
            raise RunExecutionCancelled("run cancellation requested")

    @staticmethod
    def _text_value(payload: dict[str, Any]) -> str:
        return payload_text(payload)

    @classmethod
    def append_text(cls, *, run_id, text: str, lease_token=None) -> int | None:
        if not text:
            return None
        with transaction.atomic():
            run = ChatRun.objects.select_for_update().select_related("assistant_message").get(pk=run_id)
            cls._assert_execution(run, lease_token)
            block = run.assistant_message.blocks.filter(kind="text").first()
            now = timezone.now()
            first_visible_delta = run.first_token_at is None
            if block is None:
                block = ChatMessageBlock.objects.create(
                    user=run.user,
                    thread=run.thread,
                    message=run.assistant_message,
                    kind="text",
                    status=ChatMessageBlock.Status.STREAMING,
                    revision=0,
                    order_key=1000,
                    node_role=NODE_ROLE_TIMELINE,
                    payload=text_payload(""),
                    created_at=now,
                    updated_at=now,
                )
                RunService._append_event_locked(
                    run=run,
                    event_type="block.created",
                    payload={
                        "message_id": str(run.assistant_message_id),
                        "block_id": str(block.id),
                        "kind": "text",
                        "status": "streaming",
                        "revision": 0,
                        "order_key": block.order_key,
                        "block": {
                            "id": str(block.id),
                            "kind": "text",
                            "status": "streaming",
                            "revision": 0,
                            "order_key": block.order_key,
                            "node_role": block.node_role,
                            "payload": text_payload(""),
                        },
                    },
                )
            block.payload = text_payload(f"{cls._text_value(dict(block.payload or {}))}{text}")
            block.revision += 1
            block.status = ChatMessageBlock.Status.STREAMING
            block.updated_at = now
            block.save(update_fields=["payload", "revision", "status", "updated_at", "server_updated_at"])
            if first_visible_delta:
                run.first_token_at = now
                run.save(update_fields=["first_token_at", "updated_at"])
                RunService._append_event_locked(run=run, event_type="assistant.status", payload={"state": "answering", "status": "answering"})
            RunService._append_event_locked(
                run=run,
                event_type="block.delta",
                payload={
                    "message_id": str(run.assistant_message_id),
                    "block_id": str(block.id),
                    "revision": block.revision,
                    "delta": text,
                    "content_type": "text/markdown",
                },
            )
            return block.revision

    @staticmethod
    def _deep_thought_inner(payload: dict[str, Any] | None) -> dict[str, Any]:
        wrapper = (payload or {}).get("deep_thought") or {}
        inner = wrapper.get("_0") if isinstance(wrapper, dict) else None
        return dict(inner) if isinstance(inner, dict) else {}

    @classmethod
    def append_reasoning(cls, *, run_id, text: str, lease_token=None) -> int | None:
        """Incrementally grow a single canonical deepThought Block for this Run."""
        if not text:
            return None
        with transaction.atomic():
            run = ChatRun.objects.select_for_update().select_related("assistant_message").get(pk=run_id)
            cls._assert_execution(run, lease_token)
            block = run.assistant_message.blocks.filter(kind=KIND_DEEP_THOUGHT).first()
            now = timezone.now()
            if block is None:
                block = ChatMessageBlock.objects.create(
                    user=run.user,
                    thread=run.thread,
                    message=run.assistant_message,
                    kind=KIND_DEEP_THOUGHT,
                    status=ChatMessageBlock.Status.STREAMING,
                    revision=0,
                    order_key=900,
                    node_role=NODE_ROLE_TIMELINE,
                    payload=deep_thought_payload("", None, True, "summary"),
                    created_at=now,
                    updated_at=now,
                )
                RunService._append_event_locked(
                    run=run,
                    event_type="block.created",
                    payload={
                        "message_id": str(run.assistant_message_id),
                        "block_id": str(block.id),
                        "kind": KIND_DEEP_THOUGHT,
                        "status": "streaming",
                        "revision": 0,
                        "order_key": block.order_key,
                        "block": {
                            "id": str(block.id),
                            "kind": KIND_DEEP_THOUGHT,
                            "status": "streaming",
                            "revision": 0,
                            "order_key": block.order_key,
                            "node_role": block.node_role,
                            "payload": deep_thought_payload("", None, True, "summary"),
                        },
                    },
                )
                inner_content = text
            else:
                inner_content = f"{cls._deep_thought_inner(dict(block.payload or {})).get('reasoning_content') or ''}{text}"
            block.payload = deep_thought_payload(
                reasoning_content=inner_content,
                reasoning_duration_ms=None,
                reasoning_expanded=True,
                reasoning_visibility="summary",
            )
            block.revision += 1
            block.status = ChatMessageBlock.Status.STREAMING
            block.updated_at = now
            block.save(update_fields=["payload", "revision", "status", "updated_at", "server_updated_at"])
            RunService._append_event_locked(
                run=run,
                event_type="block.delta",
                payload={
                    "message_id": str(run.assistant_message_id),
                    "block_id": str(block.id),
                    "revision": block.revision,
                    "delta": text,
                    "content_type": "text/markdown",
                },
            )
            return block.revision

    @classmethod
    def _append_run_payload(cls, *, run_id, event_type: str, payload: dict[str, Any], lease_token=None) -> None:
        """Append a replayable run-scoped event under the execution guard."""
        with transaction.atomic():
            run = ChatRun.objects.select_for_update().get(pk=run_id)
            cls._assert_execution(run, lease_token)
            RunService._append_event_locked(run=run, event_type=event_type, payload=payload or {})

    @classmethod
    def round_started(cls, *, run_id, round_id: str, index: int, call_id: str | None = None, lease_token=None) -> None:
        cls._append_run_payload(
            run_id=run_id,
            event_type="agent.round.started",
            payload={"round_id": round_id, "index": index, "call_id": call_id, "status": "running"},
            lease_token=lease_token,
        )

    @classmethod
    def round_delta(
        cls,
        *,
        run_id,
        round_id: str,
        index: int,
        channel: str,
        text_delta: str,
        lease_token=None,
    ) -> None:
        if not text_delta:
            return
        cls._append_run_payload(
            run_id=run_id,
            event_type="agent.round.delta",
            payload={"round_id": round_id, "index": index, "channel": channel, "text_delta": text_delta},
            lease_token=lease_token,
        )

    @classmethod
    def round_completed(
        cls,
        *,
        run_id,
        round_id: str,
        index: int,
        call_id: str | None,
        call_role: str,
        content: str,
        finish_reason: str,
        lease_token=None,
    ) -> None:
        cls._append_run_payload(
            run_id=run_id,
            event_type="agent.round.completed",
            payload={
                "round_id": round_id,
                "index": index,
                "call_id": call_id,
                "status": "completed",
                "call_role": call_role,
                "content": content,
                "finish_reason": finish_reason,
            },
            lease_token=lease_token,
        )

    @classmethod
    def round_failed(
        cls,
        *,
        run_id,
        round_id: str,
        index: int,
        call_id: str | None,
        error_code: str,
        retryable: bool,
        lease_token=None,
    ) -> None:
        cls._append_run_payload(
            run_id=run_id,
            event_type="agent.round.failed",
            payload={
                "round_id": round_id,
                "index": index,
                "call_id": call_id,
                "status": "failed",
                "error_code": error_code,
                "retryable": retryable,
            },
            lease_token=lease_token,
        )

    @classmethod
    def usage_updated(cls, *, run_id, usage: dict[str, Any], lease_token=None) -> None:
        if not usage:
            return
        with transaction.atomic():
            run = ChatRun.objects.select_for_update().get(pk=run_id)
            cls._assert_execution(run, lease_token)
            RunService._append_event_locked(
                run=run,
                event_type="usage.updated",
                payload={
                    "provider": run.provider,
                    "model": run.model,
                    "prompt_tokens": _usage_value(usage, "prompt_tokens", "input_tokens"),
                    "completion_tokens": _usage_value(usage, "completion_tokens", "output_tokens"),
                    "reasoning_tokens": _usage_value(usage, "reasoning_tokens"),
                    "source": "provider",
                },
            )

    @classmethod
    def finish(
        cls,
        *,
        run_id,
        status=RunStatus.COMPLETED,
        finish_reason="stop",
        error_code="",
        error_message="",
        retryable=False,
        lease_token=None,
        usage: dict[str, Any] | None = None,
        provider_request_id: str = "",
        model_calls: int = 0,
        tool_calls: int = 0,
    ):
        usage = dict(usage or {})
        with transaction.atomic():
            run = ChatRun.objects.select_for_update().select_related("assistant_message").get(pk=run_id)
            if run.is_terminal:
                return run
            if lease_token is not None and run.lease_token != lease_token:
                raise RunLeaseLost("run worker lease was replaced")
            if run.cancel_requested_at is not None:
                status = RunStatus.CANCELLED
                finish_reason = "cancelled"
                error_code = ""
                error_message = ""
                retryable = False
            lock = ChatThreadRunLock.objects.select_for_update().get(thread=run.thread)
            now = timezone.now()
            for block in run.assistant_message.blocks.filter(kind__in=[KIND_TEXT, KIND_DEEP_THOUGHT]).order_by("order_key", "created_at"):
                if block.kind == KIND_DEEP_THOUGHT:
                    inner = cls._deep_thought_inner(dict(block.payload or {}))
                    duration_ms = None
                    if block.created_at:
                        end_at = run.first_token_at or now
                        duration_ms = max(0, int((end_at - block.created_at).total_seconds() * 1000))
                    block.payload = deep_thought_payload(
                        reasoning_content=str(inner.get("reasoning_content") or ""),
                        reasoning_duration_ms=duration_ms,
                        reasoning_expanded=False,
                        reasoning_visibility=str(inner.get("reasoning_visibility") or "summary"),
                    )
                block.revision += 1
                block.status = ChatMessageBlock.Status.READY if status == RunStatus.COMPLETED else ChatMessageBlock.Status.FAILED
                block.updated_at = now
                block.save(update_fields=["payload", "revision", "status", "updated_at", "server_updated_at"] if block.kind == KIND_DEEP_THOUGHT else ["revision", "status", "updated_at", "server_updated_at"])
                RunService._append_event_locked(
                    run=run,
                    event_type="block.completed" if status == RunStatus.COMPLETED else "block.failed",
                    payload={
                        "message_id": str(run.assistant_message_id),
                        "block_id": str(block.id),
                        "kind": block.kind,
                        "revision": block.revision,
                        "status": block.status,
                        "payload_hash": _payload_hash(block.payload or {}),
                        **({"error": {"code": error_code or "generation_incomplete", "message": error_message or "generation did not complete"}} if status != RunStatus.COMPLETED else {}),
                    },
                )

            prompt_tokens = _usage_value(usage, "prompt_tokens", "input_tokens")
            completion_tokens = _usage_value(usage, "completion_tokens", "output_tokens")
            reasoning_tokens = _usage_value(usage, "reasoning_tokens")
            total_tokens = _usage_value(usage, "total_tokens") or prompt_tokens + completion_tokens
            usage_source = "provider" if usage else "unavailable"
            ChatUsageRecord.objects.update_or_create(
                run=run,
                defaults={
                    "provider": run.provider,
                    "model": run.model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "model_calls": max(0, int(model_calls)),
                    "tool_calls": max(0, int(tool_calls)),
                    "usage_source": usage_source,
                },
            )
            RunService._append_event_locked(
                run=run,
                event_type="usage.final",
                payload={
                    "provider": run.provider,
                    "model": run.model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "total_tokens": total_tokens,
                    "model_calls": max(0, int(model_calls)),
                    "tool_calls": max(0, int(tool_calls)),
                    "source": usage_source,
                },
            )
            run.finish_reason = finish_reason
            if provider_request_id:
                run.provider_request_id = provider_request_id[:128]
            RunService._finalize_locked(
                run=run,
                lock=lock,
                status=status,
                error_code=error_code,
                error_message=error_message,
                retryable=retryable,
            )
            run.save(update_fields=["finish_reason", "provider_request_id", "updated_at"])
            return run
