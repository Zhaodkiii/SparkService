from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import transaction
from django.utils import timezone

from chat_sync.ai_models import ChatAgentCheckpoint, ChatRun, ChatToolCall
from chat_sync.ai_runtime.tools.dispatcher import ToolDispatchItem
from chat_sync.ai_runtime.tools.policy import canonical_tool_args
from chat_sync.ai_runtime.tools.scoped_registry import ScopedToolRegistry
from chat_sync.models import ChatMessageBlock

from .run_service import RunService


def _short(value: Any, limit: int = 8_000) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text[:limit]


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
                "execution_key": f"{run.id}:{round_index}:{call_id}",
                "max_attempts": entry.policy.max_attempts if entry else 1,
                "provider_index": call.get("index"),
            },
        )
        rows.append(row)
        now = timezone.now()
        ChatMessageBlock.objects.get_or_create(
            user=run.user,
            thread=run.thread,
            message=run.assistant_message,
            tool_call_id=call_id,
            kind="toolCall",
            defaults={
                "status": ChatMessageBlock.Status.STREAMING,
                "revision": 1,
                "order_key": 1800 + call_index,
                "node_role": "toolExecution",
                "payload": {"tool_name": name, "arguments": args, "status": "requested"},
                "created_at": now,
                "updated_at": now,
            },
        )
        RunService._append_event_locked(run=run, event_type="tool.call.requested", payload={"tool_call_id": call_id, "tool_name": name, "round_index": round_index})
    return rows


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
        row.status = ChatToolCall.Status.COMPLETED if item.result.success else ChatToolCall.Status.FAILED
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
        ChatMessageBlock.objects.filter(message=run.assistant_message, tool_call_id=row.tool_call_id, kind="toolCall").update(
            status=ChatMessageBlock.Status.READY,
            revision=2,
            payload={"tool_name": row.tool_name, "arguments": row.arguments, "status": row.status, "error_code": error_code},
            updated_at=now,
        )
        ChatMessageBlock.objects.create(
            user=run.user,
            thread=run.thread,
            message=run.assistant_message,
            kind="toolResult",
            status=ChatMessageBlock.Status.READY,
            revision=1,
            order_key=2000 + row.call_index,
            tool_call_id=row.tool_call_id,
            node_role="toolExecution",
            payload={"tool_name": row.tool_name, "success": item.result.success, "content": _short(item.result.content), "metadata": metadata},
            created_at=now,
            updated_at=now,
        )
        RunService._append_event_locked(run=run, event_type="tool.result", payload={"tool_call_id": row.tool_call_id, "tool_name": row.tool_name, "success": item.result.success, "error_code": error_code})


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


__all__ = ["record_tool_requests", "record_tool_results", "save_agent_checkpoint"]
