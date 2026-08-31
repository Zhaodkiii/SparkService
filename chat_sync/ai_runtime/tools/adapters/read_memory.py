from __future__ import annotations

from collections import defaultdict

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone

from chat_sync.ai_memory.constants import DEFAULT_READ_TOKEN_BUDGET, DEFAULT_RECALL_COUNT
from chat_sync.ai_memory.services.memory_query_service import MemoryQueryService, clip_recall_rows
from chat_sync.ai_models.memory import AIMemory
from chat_sync.ai_runtime.protocols.tool_protocol import BaseTool, ToolDefinition, ToolResult
from chat_sync.ai_runtime.tools.policy import ToolExecutionContext

SLOT_TITLES = {
    "recent": "Recent",
    "profile": "Profile",
    "scope": "Scope",
    "preferences": "Preferences",
}


class ReadMemoryTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_memory",
            description="读取用户长期记忆，包括近期情况、稳定画像、知识范围和明确偏好。仅在个性化回答确有帮助时调用；纯事实问题或无关问题不要调用。",
            raw_parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )

    async def execute(self, *, _execution_context=None, **kwargs) -> ToolResult:
        if kwargs:
            return ToolResult(
                content="read_memory 不接受额外参数。",
                success=False,
                metadata={"error_code": "memory_payload_invalid", "activity_status": "failed"},
            )
        if not isinstance(_execution_context, ToolExecutionContext):
            return ToolResult(
                content="工具执行上下文不可用。",
                success=False,
                metadata={"error_code": "tool_context_missing", "activity_status": "failed"},
            )
        try:
            payload = await sync_to_async(_recall)(_execution_context)
        except Exception:
            return ToolResult(
                content="记忆暂时不可用。",
                success=False,
                metadata={"error_code": "memory_unavailable", "activity_status": "failed", "retryable": True},
            )
        return payload


def _recall(context: ToolExecutionContext) -> ToolResult:
    user = get_user_model().objects.filter(pk=context.user_id).first()
    if user is None:
        return ToolResult(content="记忆暂时不可用。", success=False, metadata={"error_code": "memory_unavailable"})
    rows = MemoryQueryService.recall_l3(user=user, member_id=context.member_id, max_count=DEFAULT_RECALL_COUNT)
    kept, trimmed = clip_recall_rows(rows, token_budget=DEFAULT_READ_TOKEN_BUDGET)
    if kept:
        ids = [item.id for item in kept]
        AIMemory.objects.filter(user=user, id__in=ids).update(last_used_at=timezone.now())
        _append_memory_sources(context.run_id, kept, trimmed=trimmed)
    content = _format_recall(kept) if kept else "当前没有可读取的长期记忆。"
    return ToolResult(
        content=content,
        success=True,
        sources=[
            {
                "source_id": str(item.id),
                "type": "memory",
                "version": str(item.revision),
                "content_hash": item.content_hash,
                "metadata": {
                    "layer": item.layer,
                    "document_key": item.document_key,
                    "scope_key": item.scope_key,
                    "trimmed": trimmed,
                },
            }
            for item in kept
        ],
        metadata={
            "activity_status": "succeeded" if kept else "empty",
            "count": len(kept),
            "trimmed": trimmed,
            "slots": sorted({item.document_key for item in kept}),
            "entry_ids": [str(item.id) for item in kept],
            "revisions": [item.revision for item in kept],
        },
    )


def _format_recall(rows: list[AIMemory]) -> str:
    grouped: dict[str, list[AIMemory]] = defaultdict(list)
    for item in rows:
        grouped[item.document_key].append(item)
    blocks: list[str] = []
    for key in ("recent", "profile", "scope", "preferences"):
        items = grouped.get(key) or []
        if not items:
            continue
        lines = [f"# {SLOT_TITLES[key]}"]
        for item in items:
            text = (item.content or "").strip()[:240]
            lines.append(f"- [{item.id} r{item.revision}] {text}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _append_memory_sources(run_id, rows: list[AIMemory], *, trimmed: bool) -> None:
    from chat_sync.ai_models import ChatTurnContextSnapshot

    snapshot = ChatTurnContextSnapshot.objects.filter(run_id=run_id).first()
    if snapshot is None:
        return
    existing = list(snapshot.sources or [])
    seen = {str(item.get("source_id")) for item in existing if isinstance(item, dict)}
    for item in rows:
        sid = str(item.id)
        if sid in seen:
            continue
        existing.append(
            {
                "source_id": sid,
                "type": "memory",
                "version": str(item.revision),
                "content_hash": item.content_hash,
                "metadata": {
                    "layer": item.layer,
                    "document_key": item.document_key,
                    "scope_key": item.scope_key,
                    "trimmed": trimmed,
                },
            }
        )
        seen.add(sid)
    snapshot.sources = existing
    snapshot.save(update_fields=["sources"])


__all__ = ["ReadMemoryTool"]
