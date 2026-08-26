from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import transaction
from django.utils import timezone

from chat_sync.ai_models import ChatAgentCheckpoint, ChatRun, ChatToolCall
from chat_sync.ai_runtime.tools.dispatcher import ToolDispatchItem
from chat_sync.ai_runtime.tools.policy import canonical_tool_args
from chat_sync.ai_runtime.tools.public_projector import (
    public_args,
    public_display_name,
    public_error,
    public_result_preview,
    safe_source_refs,
)
from chat_sync.ai_runtime.tools.scoped_registry import ScopedToolRegistry
from chat_sync.contracts import (
    NODE_ROLE_TOOL,
    NODE_ROLE_TOOL_PRESENTATION,
    tool_payload,
    tool_presentation_kind,
    tool_result_presentation_payload,
)
from chat_sync.models import ChatMessageBlock

from .run_service import RunService

# Entity revisions are strictly monotonic per tool call:
#   1 = requested, 2 = running, 3 = terminal.
REVISION_REQUESTED = 1
REVISION_RUNNING = 2
REVISION_TERMINAL = 3

# Round-encoded order keys keep cross-round ordering collision-free:
#   toolCall  = 1800 + round * 100 + call_index
#   toolResult = 1850 + round * 100 + call_index
TOOL_CALL_ORDER_BASE = 1800
TOOL_RESULT_ORDER_BASE = 1850
ROUND_ORDER_STRIDE = 100


def _short(value: Any, limit: int = 8_000) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text[:limit]


def _order_key(base: int, round_index: int, call_index: int) -> int:
    return base + int(round_index) * ROUND_ORDER_STRIDE + int(call_index)


def _activity_payload(
    row: ChatToolCall,
    *,
    status: str,
    revision: int,
    result_preview: str | None = None,
    source_refs: list[dict[str, Any]] | None = None,
    error: dict[str, Any] | None = None,
    duplicate_of: str | None = None,
    started_at=None,
    finished_at=None,
) -> dict[str, Any]:
    """Full safe Tool Activity projection. Raw arguments/results never enter it."""
    return {
        "tool_call_id": row.tool_call_id,
        "name": row.tool_name,
        "version": row.tool_version or "v1",
        "display_name": public_display_name(row.tool_name),
        "target": "server",
        "status": status,
        "round_index": int(row.round_index or 0),
        "call_index": int(row.call_index or 0),
        "revision": revision,
        "display_args": public_args(row.tool_name, row.arguments),
        "result_preview": result_preview,
        "source_refs": source_refs or [],
        "error": error,
        "duplicate_of": duplicate_of,
        "started_at": started_at.isoformat() if started_at else None,
        "finished_at": finished_at.isoformat() if finished_at else None,
    }


def _block_event_payload(*, run: ChatRun, block: ChatMessageBlock, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": str(run.assistant_message_id),
        "block_id": str(block.id),
        "kind": block.kind,
        "status": block.status,
        "revision": block.revision,
        "order_key": block.order_key,
        "tool_call_id": block.tool_call_id or None,
        "block": {
            "id": str(block.id),
            "kind": block.kind,
            "status": block.status,
            "revision": block.revision,
            "order_key": block.order_key,
            "node_role": block.node_role,
            "tool_call_id": block.tool_call_id or None,
            "payload": payload,
        },
    }


def _tool_block_payload(row: ChatToolCall) -> dict[str, Any]:
    """Canonical ``tool`` block payload (kind=tool, node_role=tool)."""
    display_args = public_args(row.tool_name, row.arguments)
    invocation: dict[str, str] | None = None
    if isinstance(display_args, dict):
        invocation = {
            str(key): json.dumps(value, ensure_ascii=False, default=str)
            for key, value in display_args.items()
        }
    content = json.dumps(display_args, ensure_ascii=False, default=str) if display_args else ""
    return tool_payload(
        name=public_display_name(row.tool_name),
        content=content,
        invocation_arguments=invocation,
    )


def _tool_result_block_payload(
    row: ChatToolCall,
    *,
    status: str,
    success: bool,
    result_preview: str | None,
    source_refs: list[dict[str, Any]],
    error: dict[str, Any] | None,
) -> dict[str, Any]:
    return tool_result_presentation_payload(
        tool_name=row.tool_name,
        display_name=public_display_name(row.tool_name),
        result_preview=result_preview,
        source_refs=source_refs,
    )


def _save_block(block: ChatMessageBlock, *, payload: dict[str, Any], status: str, revision: int, now) -> ChatMessageBlock:
    block.payload = payload
    block.status = status
    block.revision = revision
    block.updated_at = now
    block.save(update_fields=["payload", "status", "revision", "updated_at", "server_updated_at"])
    return block


@transaction.atomic
def record_tool_requests(run_id, round_index: int, calls: list[dict[str, Any]], registry: ScopedToolRegistry) -> list[ChatToolCall]:
    run = ChatRun.objects.select_for_update().select_related("assistant_message").get(id=run_id)
    rows: list[ChatToolCall] = []
    for call_index, call in enumerate(calls):
        name = str(call.get("name") or "")[:128]
        entry = registry.get(name)
        args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
        call_id = str(call.get("id") or f"tool_call_{round_index}_{call_index}")[:128]
        args_hash = canonical_tool_args(name, entry.policy.version if entry else "", args)
        row, _ = ChatToolCall.objects.get_or_create(
            run=run,
            tool_call_id=call_id,
            defaults={
                "tool_name": name,
                "tool_version": entry.policy.version if entry else "",
                "target": entry.policy.target if entry else "server",
                "arguments": args,
                "round_index": round_index,
                "call_index": call_index,
                "canonical_name": name,
                "arguments_hash": args_hash,
                "schema_hash": entry.schema_hash if entry else "",
                "policy_version": entry.policy.version if entry else "",
                "execution_key": f"{run.id}:{args_hash}",
                "max_attempts": entry.policy.max_attempts if entry else 1,
                "provider_index": call.get("index"),
            },
        )
        rows.append(row)
        now = timezone.now()
        block, _created = ChatMessageBlock.objects.get_or_create(
            user=run.user,
            thread=run.thread,
            message=run.assistant_message,
            tool_call_id=call_id,
            kind="tool",
            defaults={
                "status": ChatMessageBlock.Status.STREAMING,
                "revision": REVISION_REQUESTED,
                "order_key": _order_key(TOOL_CALL_ORDER_BASE, round_index, call_index),
                "node_role": NODE_ROLE_TOOL,
                "payload": _tool_block_payload(row),
                "created_at": now,
                "updated_at": now,
            },
        )
        activity = _activity_payload(row, status="requested", revision=REVISION_REQUESTED)
        RunService._append_event_locked(
            run=run,
            event_type="tool.call.requested",
            payload={"tool_call_id": call_id, "tool_name": name, "round_index": round_index, "activity": activity},
        )
        RunService._append_event_locked(
            run=run,
            event_type="block.created",
            payload=_block_event_payload(run=run, block=block, payload=dict(block.payload or {})),
        )
    return rows


@transaction.atomic
def mark_tool_started(run_id, tool_call_id: str) -> None:
    """Persist + broadcast the running transition before the executor starts."""
    run = ChatRun.objects.select_for_update().select_related("assistant_message").get(id=run_id)
    row = ChatToolCall.objects.select_for_update().filter(run=run, tool_call_id=str(tool_call_id)[:128]).first()
    if row is None or row.status not in {ChatToolCall.Status.REQUESTED, ChatToolCall.Status.RUNNING}:
        return
    now = timezone.now()
    row.status = ChatToolCall.Status.RUNNING
    row.started_at = row.started_at or now
    row.save(update_fields=["status", "started_at", "updated_at"])
    RunService._append_event_locked(
        run=run,
        event_type="tool.call.started",
        payload={
            "tool_call_id": row.tool_call_id,
            "status": "running",
            "revision": REVISION_RUNNING,
            "started_at": row.started_at.isoformat() if row.started_at else None,
        },
    )
    block = (
        ChatMessageBlock.objects.select_for_update()
        .filter(message=run.assistant_message, tool_call_id=row.tool_call_id, kind="tool")
        .first()
    )
    if block is not None:
        _save_block(
            block,
            payload=_tool_block_payload(row),
            status=ChatMessageBlock.Status.STREAMING,
            revision=REVISION_RUNNING,
            now=now,
        )
        RunService._append_event_locked(
            run=run,
            event_type="block.updated",
            payload=_block_event_payload(run=run, block=block, payload=dict(block.payload or {})),
        )


@transaction.atomic
def record_tool_progress(run_id, tool_call_id: str, message: str, percent=None) -> None:
    """Persist + broadcast a transient progress patch for an active tool call."""
    run = ChatRun.objects.select_for_update().select_related("assistant_message").get(id=run_id)
    row = ChatToolCall.objects.select_for_update().filter(run=run, tool_call_id=str(tool_call_id)[:128]).first()
    if row is None or row.status not in {ChatToolCall.Status.REQUESTED, ChatToolCall.Status.RUNNING}:
        return
    percent_value = None
    if isinstance(percent, (int, float)) and 0 <= percent <= 100:
        percent_value = int(percent)
    RunService._append_event_locked(
        run=run,
        event_type="tool.call.progress",
        payload={
            "tool_call_id": row.tool_call_id,
            "status": "running",
            "revision": REVISION_RUNNING,
            "progress_message": str(message)[:512],
            "progress_percent": percent_value,
        },
    )


@transaction.atomic
def record_tool_results(run_id, items: list[ToolDispatchItem]) -> None:
    run = ChatRun.objects.select_for_update().select_related("assistant_message", "thread", "user").get(id=run_id)
    now = timezone.now()
    for item in items:
        row = ChatToolCall.objects.select_for_update().filter(run=run, tool_call_id=item.call_id).first()
        if row is None:
            continue
        metadata = dict(item.result.metadata or {})
        error_code = str(metadata.get("error_code") or "")[:64]
        success = bool(item.result.success)
        status = ChatToolCall.Status.COMPLETED if success else ChatToolCall.Status.FAILED
        row.status = status
        row.attempt_count = max(1, row.attempt_count + 1)
        row.result_content = _short(item.result.content)
        row.result_summary = _short(item.result.content, 512)
        row.result_metadata = metadata
        row.source_refs = item.result.sources[:32]
        row.error_code = error_code
        row.error_message = _short(item.result.content, 512) if error_code else ""
        row.retryable = bool(metadata.get("retryable"))
        row.started_at = row.started_at or now
        row.finished_at = now
        if item.duplicate_of:
            row.duplicate_of_id = ChatToolCall.objects.filter(run=run, tool_call_id=item.duplicate_of).values_list("id", flat=True).first()
        row.save()
        duplicate_of = str(item.duplicate_of) if item.duplicate_of else None
        source_refs = safe_source_refs(item.result.sources)
        error = public_error(error_code)
        result_preview = public_result_preview(
            row.tool_name,
            success=success,
            arguments=row.arguments,
            source_refs=source_refs,
            duplicate=bool(item.duplicate_of),
        )
        activity = _activity_payload(
            row,
            status=status.lower(),
            revision=REVISION_TERMINAL,
            result_preview=result_preview,
            source_refs=source_refs,
            error=error,
            duplicate_of=duplicate_of,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )
        RunService._append_event_locked(
            run=run,
            event_type="tool.result",
            payload={
                "tool_call_id": row.tool_call_id,
                "tool_name": row.tool_name,
                "success": success,
                "error_code": (error or {}).get("code", ""),
                "activity": activity,
            },
        )
        call_block = (
            ChatMessageBlock.objects.select_for_update()
            .filter(message=run.assistant_message, tool_call_id=row.tool_call_id, kind="tool")
            .first()
        )
        if call_block is not None:
            _save_block(
                call_block,
                payload=_tool_block_payload(row),
                status=ChatMessageBlock.Status.READY if success else ChatMessageBlock.Status.FAILED,
                revision=REVISION_TERMINAL,
                now=now,
            )
            RunService._append_event_locked(
                run=run,
                event_type="block.updated",
                payload=_block_event_payload(run=run, block=call_block, payload=dict(call_block.payload or {})),
            )
        result_kind = tool_presentation_kind(row.tool_name)
        result_block = ChatMessageBlock.objects.create(
            user=run.user,
            thread=run.thread,
            message=run.assistant_message,
            kind=result_kind,
            status=ChatMessageBlock.Status.READY if success else ChatMessageBlock.Status.FAILED,
            revision=1,
            order_key=_order_key(TOOL_RESULT_ORDER_BASE, row.round_index, row.call_index),
            tool_call_id=row.tool_call_id,
            node_role=NODE_ROLE_TOOL_PRESENTATION,
            payload=_tool_result_block_payload(
                row,
                status=status.lower(),
                success=success,
                result_preview=result_preview,
                source_refs=source_refs,
                error=error,
            ),
            created_at=now,
            updated_at=now,
        )
        RunService._append_event_locked(
            run=run,
            event_type="block.created",
            payload=_block_event_payload(run=run, block=result_block, payload=dict(result_block.payload or {})),
        )
        RunService._append_event_locked(
            run=run,
            event_type="block.completed" if success else "block.failed",
            payload={
                "message_id": str(run.assistant_message_id),
                "block_id": str(result_block.id),
                "kind": result_kind,
                "status": result_block.status,
                "revision": 2,
                "order_key": result_block.order_key,
                "tool_call_id": row.tool_call_id,
            },
        )


@transaction.atomic
def converge_cancelled_tool_calls(run_id) -> int:
    """Converge non-terminal tool calls to cancelled when the Run is cancelled."""
    run = ChatRun.objects.select_for_update().select_related("assistant_message").get(id=run_id)
    now = timezone.now()
    rows = ChatToolCall.objects.select_for_update().filter(
        run=run,
        status__in=[ChatToolCall.Status.REQUESTED, ChatToolCall.Status.RUNNING],
    )
    converged = 0
    for row in rows:
        row.status = ChatToolCall.Status.CANCELLED
        row.finished_at = now
        row.save(update_fields=["status", "finished_at", "updated_at"])
        activity = _activity_payload(
            row,
            status="cancelled",
            revision=REVISION_TERMINAL,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )
        RunService._append_event_locked(
            run=run,
            event_type="tool.call.cancelled",
            payload={
                "tool_call_id": row.tool_call_id,
                "status": "cancelled",
                "revision": REVISION_TERMINAL,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "activity": activity,
            },
        )
        block = (
            ChatMessageBlock.objects.select_for_update()
            .filter(message=run.assistant_message, tool_call_id=row.tool_call_id, kind="tool")
            .first()
        )
        if block is not None:
            _save_block(
                block,
                payload=_tool_block_payload(row),
                status=ChatMessageBlock.Status.FAILED,
                revision=REVISION_TERMINAL,
                now=now,
            )
            RunService._append_event_locked(
                run=run,
                event_type="block.updated",
                payload=_block_event_payload(run=run, block=block, payload=dict(block.payload or {})),
            )
        converged += 1
    return converged


@transaction.atomic
def save_agent_checkpoint(run_id, *, transcript: list[dict[str, Any]], next_round_index: int, tool_steps: int, context_snapshot_id=None, context_hash: str = "", tool_manifest_hash: str = "") -> ChatAgentCheckpoint:
    run = ChatRun.objects.select_for_update().get(id=run_id)
    serialized = json.dumps(transcript, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    checkpoint, _ = ChatAgentCheckpoint.objects.select_for_update().get_or_create(run=run)
    checkpoint.revision += 1
    checkpoint.next_round_index = next_round_index
    checkpoint.tool_steps = tool_steps
    checkpoint.transcript = transcript[-64:]
    checkpoint.context_snapshot_id = context_snapshot_id
    checkpoint.context_hash = context_hash
    checkpoint.tool_manifest_hash = tool_manifest_hash
    checkpoint.transcript_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    checkpoint.status = ChatAgentCheckpoint.Status.READY
    checkpoint.save()
    return checkpoint


__all__ = [
    "converge_cancelled_tool_calls",
    "mark_tool_started",
    "record_tool_progress",
    "record_tool_requests",
    "record_tool_results",
    "save_agent_checkpoint",
]
