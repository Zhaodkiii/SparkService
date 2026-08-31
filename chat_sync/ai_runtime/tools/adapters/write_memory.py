from __future__ import annotations

import logging
import re
import uuid

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.db import transaction

from chat_sync.ai_memory.constants import MAX_CONTENT_CHARS
from chat_sync.ai_memory.services.keys import (
    clamp_content,
    compute_content_hash,
    compute_dedup_key,
    compute_normalized_key,
    compute_scope_key,
    mutation_id_from_key,
)
from chat_sync.ai_memory.services.idempotency_service import IdempotencyConflict, IdempotencyService, compute_request_hash
from chat_sync.ai_memory.services.payloads import memory_to_snapshot
from chat_sync.ai_models.memory import (
    AIMemory,
    MemoryConfirmationStatus,
    MemoryLayer,
    MemoryMutationOperation,
    MemoryScope,
    MemorySensitivity,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from chat_sync.ai_runtime.protocols.tool_protocol import BaseTool, ToolDefinition, ToolResult
from chat_sync.ai_runtime.tools.policy import ToolExecutionContext, canonical_tool_args

logger = logging.getLogger("chat_sync.ai.tools")

FORBIDDEN_PATTERNS = (
    re.compile(r"验证码|密码|api[_ ]?key|secret|token|身份证|passwd|password", re.I),
    re.compile(r"过敏|高血压|糖尿病|诊断|血糖|血压|肿瘤|癌症|传染病"),
    re.compile(r"今天心情|心情不好|情绪低落"),
)


class WriteMemoryTool(BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_memory",
            description="仅当用户明确表达长期回答偏好时保存新记忆。不得推测，不得保存医疗判断、身份推断、短期情绪或凭证。不得编辑已有记忆。",
            raw_parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 1, "maxLength": 240},
                    "reason": {"type": "string", "maxLength": 160},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        )

    async def execute(self, *, text: str = "", reason: str = "", _execution_context=None, **kwargs) -> ToolResult:
        if not isinstance(_execution_context, ToolExecutionContext):
            return ToolResult(
                content="工具执行上下文不可用。",
                success=False,
                metadata={"error_code": "tool_context_missing", "activity_status": "failed"},
            )
        try:
            return await sync_to_async(_write)(_execution_context, text, reason)
        except Exception:
            logger.exception("write_memory failed run=%s", _execution_context.run_id)
            return ToolResult(
                content="记忆暂时不可用。",
                success=False,
                metadata={"error_code": "memory_unavailable", "activity_status": "failed", "retryable": True},
            )


def _write(context: ToolExecutionContext, text: str, reason: str) -> ToolResult:
    user = get_user_model().objects.filter(pk=context.user_id).first()
    if user is None:
        return _fail("memory_unavailable", "记忆暂时不可用。", retryable=True)
    content = clamp_content(text)
    if not content:
        return _fail("memory_invalid_preference", "不是可保存的长期偏好。")
    if _is_forbidden(content):
        return _fail("memory_invalid_preference", "不是可保存的长期偏好。")

    execution_key = f"{context.run_id}:{canonical_tool_args('write_memory', 'v1', {'text': content, 'reason': reason or ''})}"
    mutation_id = mutation_id_from_key(execution_key)
    memory_payload = {
        "scope": MemoryScope.ACCOUNT,
        "layer": MemoryLayer.L3,
        "document_key": "preferences",
        "section_key": "answer_style",
        "memory_type": MemoryType.PREFERENCE,
        "content": content,
        "source": MemorySource.USER,
    }
    request_hash = compute_request_hash(
        operation=MemoryMutationOperation.CREATE,
        memory_id="new",
        base_revision=None,
        memory=memory_payload,
    )
    try:
        with transaction.atomic():
            replay = IdempotencyService.check_replay(user=user, mutation_id=mutation_id, request_hash=request_hash)
            if replay is not None:
                snapshot = dict(replay.result_snapshot or {})
                replay_action = snapshot.get("action") or "duplicate"
                if replay_action == "added":
                    replay_action = "duplicate"
                return _ok(replay_action, snapshot, deduplicated=True)

            result = _add_preference(user=user, content=content, run_id=context.run_id)
            snapshot = result["snapshot"]
            IdempotencyService.record(
                user=user,
                mutation_id=mutation_id,
                memory_id=snapshot["id"],
                operation=MemoryMutationOperation.CREATE,
                request_hash=request_hash,
                base_revision=None,
                result_revision=int(snapshot.get("revision") or 0),
                result_snapshot={**snapshot, "action": result["action"]},
            )
            return _ok(result["action"], snapshot, deduplicated=result["action"] == "duplicate")
    except IdempotencyConflict:
        return _fail("memory_unavailable", "记忆写入冲突，请稍后重试。")


def _add_preference(*, user, content: str, run_id) -> dict:
    scope_key = compute_scope_key(scope=MemoryScope.ACCOUNT)
    normalized_key = compute_normalized_key(memory_type=MemoryType.PREFERENCE, content=content)
    dedup_key = compute_dedup_key(
        user_id=user.id,
        scope_key=scope_key,
        layer=MemoryLayer.L3,
        document_key="preferences",
        memory_type=MemoryType.PREFERENCE,
        normalized_key=normalized_key,
    )
    existing = AIMemory.objects.select_for_update().filter(user=user, dedup_key=dedup_key, is_deleted=False).first()
    if existing is not None:
        return {"action": "duplicate", "snapshot": memory_to_snapshot(existing)}
    memory = AIMemory.objects.create(
        id=uuid.uuid4(),
        user=user,
        scope=MemoryScope.ACCOUNT,
        scope_key=scope_key,
        layer=MemoryLayer.L3,
        document_key="preferences",
        section_key="answer_style",
        memory_type=MemoryType.PREFERENCE,
        normalized_key=normalized_key,
        dedup_key=dedup_key,
        title=content[:20],
        content=content,
        structured_value={},
        content_hash=compute_content_hash(content=content, structured_value={}),
        source=MemorySource.USER,
        confirmation_status=MemoryConfirmationStatus.NOT_REQUIRED,
        sensitivity=MemorySensitivity.NORMAL,
        status=MemoryStatus.ACTIVE,
        revision=1,
        created_by_run_id=_safe_run_id(run_id),
    )
    return {"action": "added", "snapshot": memory_to_snapshot(memory)}


def _safe_run_id(run_id):
    if not run_id:
        return None
    try:
        from chat_sync.ai_models import ChatRun

        if ChatRun.objects.filter(pk=run_id).exists():
            return run_id
    except Exception:
        return None
    return None


def _is_forbidden(content: str) -> bool:
    if len(content) > MAX_CONTENT_CHARS:
        return True
    return any(pattern.search(content) for pattern in FORBIDDEN_PATTERNS)


def _ok(action: str, snapshot: dict, *, deduplicated: bool) -> ToolResult:
    return ToolResult(
        content=f"记忆已{ {'added': '保存', 'duplicate': '存在'} .get(action, '处理')}。",
        success=True,
        metadata={
            "activity_status": "succeeded",
            "ok": True,
            "action": action,
            "entry_id": snapshot.get("id"),
            "revision": snapshot.get("revision"),
            "deduplicated": deduplicated,
        },
    )


def _fail(code: str, message: str, *, retryable: bool = False) -> ToolResult:
    return ToolResult(
        content=message,
        success=False,
        metadata={"error_code": code, "activity_status": "failed", "retryable": retryable},
    )


__all__ = ["WriteMemoryTool"]
