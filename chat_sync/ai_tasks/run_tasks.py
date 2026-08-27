from __future__ import annotations

import logging
import uuid
import asyncio
from contextlib import suppress
from typing import Awaitable, Callable

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from chat_sync.ai_models import ChatAgentCheckpoint, RunStatus
from chat_sync.ai_services.run_service import RunService
from chat_sync.ai_services.stream_writer import RunExecutionCancelled, RunLeaseLost, StreamWriter
from chat_sync.ai_runtime.agentic.loop import run_agentic_loop
from chat_sync.ai_runtime.providers.error_adapter import adapt_error
from chat_sync.ai_runtime.providers.exceptions import LLMAPIError
from chat_sync.ai_runtime.providers.factory import create_chat_gateway, resolve_chat_route
from chat_sync.ai_services.context.context_builder import ContextBuildError, build_context_for_run
from asgiref.sync import sync_to_async
from chat_sync.ai_runtime.tools.registry import ToolRegistry, build_server_tool_registry
from chat_sync.ai_runtime.tools.scoped_registry import ScopedToolRegistry
from chat_sync.ai_runtime.tools.policy import ToolExecutionContext
from chat_sync.ai_runtime.tools.composition import provider_tool_schemas
from chat_sync.ai_services.tool_state_service import (
    converge_cancelled_tool_calls,
    mark_tool_started,
    record_tool_progress,
    record_tool_requests,
    record_tool_results,
    save_agent_checkpoint,
)
from chat_sync.ai_services.pending_interaction_service import PendingInteractionService
from chat_sync.contracts import payload_text

logger = logging.getLogger("chat_sync.ai.tasks")


def _context_snapshot_id(run_record) -> int | None:
    """``ChatRun.context_snapshot`` is the reverse accessor of a OneToOneField
    declared on ``ChatTurnContextSnapshot`` (not a forward FK), so ``ChatRun``
    has no ``context_snapshot_id`` shortcut attribute and accessing a missing
    related row raises ``DoesNotExist`` rather than returning ``None``."""
    try:
        return run_record.context_snapshot.id
    except ObjectDoesNotExist:
        return None


class AsyncTextDeltaBuffer:
    """Flush text after 50 ms or 256 chars, whichever comes first."""

    def __init__(self, writer: Callable[[str], Awaitable[None]], *, max_chars: int = 256, max_delay: float = 0.05):
        self.writer = writer
        self.max_chars = max_chars
        self.max_delay = max_delay
        self._parts: list[str] = []
        self._size = 0
        self._lock = asyncio.Lock()
        self._timer: asyncio.Task | None = None
        self._error: BaseException | None = None

    async def add(self, text: str) -> None:
        if not text:
            return
        await self._raise_if_failed()
        payload = ""
        timer = None
        async with self._lock:
            self._parts.append(text)
            self._size += len(text)
            if self._size >= self.max_chars:
                payload = self._take_locked()
                timer, self._timer = self._timer, None
            elif self._timer is None:
                self._timer = asyncio.create_task(self._flush_after_delay())
        if timer is not None:
            timer.cancel()
            with suppress(asyncio.CancelledError):
                await timer
        if payload:
            await self.writer(payload)

    async def _flush_after_delay(self) -> None:
        try:
            await asyncio.sleep(self.max_delay)
            async with self._lock:
                payload = self._take_locked()
                self._timer = None
            if payload:
                await self.writer(payload)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # surfaced on the provider loop or close
            self._error = exc

    def _take_locked(self) -> str:
        payload = "".join(self._parts)
        self._parts = []
        self._size = 0
        return payload

    async def _raise_if_failed(self) -> None:
        if self._error is not None:
            error, self._error = self._error, None
            raise error

    async def close(self) -> None:
        timer = None
        async with self._lock:
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()
            with suppress(asyncio.CancelledError):
                await timer
        await self._raise_if_failed()
        async with self._lock:
            payload = self._take_locked()
        if payload:
            await self.writer(payload)
        await self._raise_if_failed()


@shared_task(bind=True, name="chat_sync.ai_tasks.run_tasks.run_chat", autoretry_for=(), max_retries=0)
def run_chat(self, run_id: str, expected_generation: int | None = None, request_id: str = ""):
    executor = getattr(settings, "CHAT_AI_RUN_EXECUTOR", "disabled")
    if executor not in {"mock", "provider"}:
        logger.info("chat_run.skipped run_id=%s executor=disabled", run_id)
        return {"status": "skipped", "reason": "executor_disabled", "run_id": run_id}
    try:
        parsed_run_id = uuid.UUID(str(run_id))
    except ValueError:
        return {"status": "failed", "reason": "invalid_run_id", "run_id": run_id}
    run = RunService.claim_for_execution(run_id=parsed_run_id, expected_generation=expected_generation)
    if run is None:
        return {"status": "noop", "run_id": run_id}
    if run.cancel_requested_at is not None:
        final = RunService.finalize_mock(run_id=parsed_run_id, status=RunStatus.CANCELLED)
        return {"status": final.status if final else RunStatus.CANCELLED, "run_id": run_id}
    if executor == "provider":
        try:
            return asyncio.run(
                _execute_provider(
                    parsed_run_id,
                    run.request_snapshot or {},
                    lease_token=run.lease_token,
                    request_id=request_id,
                )
            )
        finally:
            from django.db import connections
            connections.close_all()
    outcome = getattr(settings, "CHAT_AI_MOCK_OUTCOME", "success")
    if outcome == "failure":
        final = RunService.finalize_mock(
            run_id=parsed_run_id,
            status=RunStatus.FAILED,
            error_code="chat_mock_failure",
            error_message="mock executor failure",
        )
    else:
        final = RunService.finalize_mock(run_id=parsed_run_id, status=RunStatus.COMPLETED)
    return {"status": final.status if final else RunStatus.FAILED, "run_id": run_id}


def _history_messages(run_id):
    from chat_sync.ai_models import ChatRun
    run = ChatRun.objects.select_related("thread").get(pk=run_id)
    limit = getattr(settings, "CHAT_AI_HISTORY_MESSAGE_LIMIT", 6)
    messages = [{"role": "system", "content": "你是 Spark 健康助手。只回答用户问题，不输出隐藏推理。"}]
    rows = list(run.thread.messages.filter(role__in=["user", "assistant"], tombstone=False).order_by("-created_at", "-id")[: limit + 1])
    for message in reversed(rows):
        block = message.blocks.filter(kind="text", status__in=["ready", "streaming"]).order_by("order_key", "created_at").first()
        # Message blocks use the iOS tagged payload shape: {"text": {"_0": "..."}}.
        # Reading the database column directly silently turns this into a dict and
        # sends malformed history to the provider.
        text = payload_text(block.payload) if block else ""
        if message.id == run.user_message_id:
            text = (run.request_snapshot or {}).get("content", text)
        if text:
            messages.append({"role": "user" if message.role == "user" else "assistant", "content": text})
    return messages


async def _execute_provider(run_id, snapshot, *, lease_token, request_id: str = ""):
    try:
        route = await sync_to_async(resolve_chat_route, thread_sensitive=True)()
        await sync_to_async(_save_route, thread_sensitive=True)(run_id, route)
        gateway = create_chat_gateway(route)
        try:
            context = await sync_to_async(build_context_for_run, thread_sensitive=True)(run_id)
            checkpoint = await sync_to_async(
                lambda: ChatAgentCheckpoint.objects.filter(run_id=run_id, status=ChatAgentCheckpoint.Status.READY).first(),
                thread_sensitive=True,
            )()
            messages = list(checkpoint.transcript) if checkpoint and checkpoint.transcript else list(context.messages)
        except ContextBuildError as exc:
            final = await sync_to_async(StreamWriter.finish, thread_sensitive=True)(
                run_id=run_id,
                status=RunStatus.FAILED,
                error_code=exc.code,
                error_message=str(exc),
                retryable=False,
                lease_token=lease_token,
            )
            return {"status": final.status, "run_id": str(run_id)}

        from chat_sync.ai_models import ChatRun
        run_record = await sync_to_async(
            lambda: ChatRun.objects.select_related("thread", "user", "context_snapshot").get(pk=run_id),
            thread_sensitive=True,
        )()
        tool_names = [str(item["name"]) for item in (context.tool_manifest or []) if item.get("name")]
        offer_tools = bool(tool_names and route.supports_tool_use)
        tool_schemas = provider_tool_schemas(context.tool_manifest) if offer_tools else []
        try:
            manifest_hash = str(run_record.context_snapshot.tool_manifest_hash or "")
        except ObjectDoesNotExist:
            manifest_hash = ""
        logger.info(
            "chat_run.provider_tools run_id=%s manifest_hash=%s tool_count=%s",
            run_id,
            manifest_hash,
            len(tool_schemas),
        )
        registry = ScopedToolRegistry(
            build_server_tool_registry() if offer_tools else ToolRegistry(),
            tool_names if offer_tools else [],
        )
        execution_context = ToolExecutionContext(
            run_id=str(run_id),
            thread_id=str(run_record.thread_id),
            user_id=run_record.user_id,
            member_id=run_record.thread.member_id,
            context_snapshot_id=_context_snapshot_id(run_record),
            context_hash=context.context_hash,
            request_id=request_id,
        )

        visible = False
        usage: dict[str, int] = {}
        finish_reason = "stop"
        provider_request_id = ""
        model_calls = 0
        tool_calls = 0
        current_round = 0

        async def ensure_running() -> None:
            state = await sync_to_async(RunService.heartbeat_execution, thread_sensitive=True)(
                run_id=run_id,
                lease_token=lease_token,
            )
            if state == "cancelled":
                raise RunExecutionCancelled("run cancellation requested")
            if state != "running":
                raise RunLeaseLost("run worker lease was replaced")

        async def write_text(text: str) -> None:
            nonlocal visible
            await ensure_running()
            visible = True
            await sync_to_async(StreamWriter.append_text, thread_sensitive=True)(
                run_id=run_id,
                text=text,
                lease_token=lease_token,
            )

        async def write_reasoning(text: str) -> None:
            await ensure_running()
            await sync_to_async(StreamWriter.round_delta, thread_sensitive=True)(
                run_id=run_id,
                round_id=str(current_round),
                index=current_round,
                channel="public_reasoning_summary",
                text_delta=text,
                lease_token=lease_token,
            )
            await sync_to_async(StreamWriter.append_reasoning, thread_sensitive=True)(
                run_id=run_id,
                text=text,
                lease_token=lease_token,
            )

        text_buffer = AsyncTextDeltaBuffer(write_text)
        reasoning_buffer = AsyncTextDeltaBuffer(write_reasoning)

        async def on_tool_calls(round_index, calls):
            nonlocal tool_calls
            tool_calls += len(calls)
            await sync_to_async(record_tool_requests, thread_sensitive=True)(run_id, round_index, calls, registry)

        async def on_tool_started(call_id):
            await sync_to_async(mark_tool_started, thread_sensitive=True)(run_id, call_id)

        async def on_progress(call_id, message, percent):
            await sync_to_async(record_tool_progress, thread_sensitive=True)(run_id, call_id, message, percent)

        async def on_narration_delta(round_index, delta):
            await sync_to_async(StreamWriter.round_delta, thread_sensitive=True)(
                run_id=run_id,
                round_id=str(round_index),
                index=round_index,
                channel="assistant_content",
                text_delta=delta,
                lease_token=lease_token,
            )

        async def on_reasoning_delta(round_index, delta):
            nonlocal current_round
            if round_index != current_round:
                await reasoning_buffer.close()
                current_round = round_index
            await reasoning_buffer.add(delta)

        async def on_tool_results(round_index, items):
            await sync_to_async(record_tool_results, thread_sensitive=True)(run_id, items)
            await sync_to_async(save_agent_checkpoint, thread_sensitive=True)(
                run_id,
                transcript=messages,
                next_round_index=round_index + 1,
                tool_steps=len(items),
                context_snapshot_id=_context_snapshot_id(run_record),
                context_hash=context.context_hash,
            )

        async def on_final_chunk(delta: str) -> None:
            await text_buffer.add(delta)

        async def on_final_text(_text: str) -> None:
            return

        async def on_round(trace):
            nonlocal model_calls, provider_request_id, finish_reason
            round_id = str(trace.index)
            if trace.event == "started":
                await sync_to_async(StreamWriter.round_started, thread_sensitive=True)(
                    run_id=run_id, round_id=round_id, index=trace.index, lease_token=lease_token,
                )
            elif trace.event == "completed":
                model_calls += 1
                if trace.call_id:
                    provider_request_id = trace.call_id
                if trace.finish_reason:
                    finish_reason = trace.finish_reason
                if trace.usage:
                    usage.update(trace.usage)
                    await sync_to_async(StreamWriter.usage_updated, thread_sensitive=True)(
                        run_id=run_id, usage=usage, lease_token=lease_token,
                    )
                await sync_to_async(StreamWriter.round_completed, thread_sensitive=True)(
                    run_id=run_id, round_id=round_id, index=trace.index, call_id=trace.call_id or None,
                    call_role=trace.call_role, content=trace.content, finish_reason=trace.finish_reason,
                    lease_token=lease_token,
                )
            elif trace.event == "failed":
                model_calls += 1
                await sync_to_async(StreamWriter.round_failed, thread_sensitive=True)(
                    run_id=run_id, round_id=round_id, index=trace.index, call_id=trace.call_id or None,
                    error_code=trace.error_code, retryable=trace.retryable, lease_token=lease_token,
                )

        async def on_pause(round_index, item, transcript):
            raw_pause = item.result.pause_for_user or {}
            await sync_to_async(PendingInteractionService.pause_for_tool, thread_sensitive=True)(
                run_id=run_id,
                tool_call_id=item.call_id,
                kind=str(raw_pause.get("kind") or "ask_user"),
                request_schema=dict(raw_pause.get("request_schema") or raw_pause.get("schema") or {}),
                required_platform=str(raw_pause.get("required_platform") or ""),
                required_capability=str(raw_pause.get("required_capability") or ""),
                tool_version=str(raw_pause.get("tool_version") or "v1"),
                expires_in_seconds=int(raw_pause.get("expires_in_seconds") or 600),
                lease_token=run_record.lease_token,
            )

        attempts = max(1, int(getattr(settings, "CHAT_AI_PROVIDER_MAX_ATTEMPTS", 2)))
        deadline_at = asyncio.get_running_loop().time() + float(getattr(settings, "CHAT_AI_RUN_DEADLINE_SECONDS", 180))
        classify_chars = int(getattr(settings, "CHAT_AI_AGENTIC_STREAM_CLASSIFY_CHARS", 40)) if offer_tools else 0
        classify_window = int(getattr(settings, "CHAT_AI_AGENTIC_STREAM_CLASSIFY_WINDOW_MS", 150)) if offer_tools else 0

        for attempt in range(attempts):
            try:
                agentic_outcome = await asyncio.wait_for(
                    run_agentic_loop(
                        gateway,
                        messages,
                        registry=registry,
                        tool_schemas=tool_schemas,
                        execution_context=execution_context,
                        on_tool_calls=on_tool_calls,
                        on_tool_started=on_tool_started,
                        on_progress=on_progress,
                        on_narration_delta=on_narration_delta,
                        on_reasoning_delta=on_reasoning_delta,
                        on_tool_results=on_tool_results,
                        on_pause=on_pause,
                        on_final_text=on_final_text,
                        on_final_chunk=on_final_chunk,
                        on_round=on_round,
                        max_rounds=int(getattr(settings, "CHAT_AI_AGENT_MAX_ROUNDS", 8)),
                        max_calls_per_round=int(getattr(settings, "CHAT_AI_TOOL_MAX_CALLS_PER_ROUND", 8)),
                        max_concurrency=int(getattr(settings, "CHAT_AI_TOOL_MAX_CONCURRENCY", 4)),
                        stream_classify_chars=classify_chars,
                        stream_classify_window_ms=classify_window,
                    ),
                    timeout=max(0.001, deadline_at - asyncio.get_running_loop().time()),
                )
                if getattr(agentic_outcome, "kind", "") == "paused":
                    with suppress(Exception):
                        await reasoning_buffer.close()
                    with suppress(Exception):
                        await text_buffer.close()
                    return {
                        "status": RunStatus.WAITING_FOR_USER_INPUT if (agentic_outcome.pause and agentic_outcome.pause.kind == "ask_user") else RunStatus.WAITING_FOR_CLIENT_TOOL,
                        "run_id": str(run_id),
                    }
                await reasoning_buffer.close()
                await text_buffer.close()
                if not visible:
                    raise LLMAPIError("provider returned no visible text")
                await ensure_running()
                final = await sync_to_async(StreamWriter.finish, thread_sensitive=True)(
                    run_id=run_id,
                    status=RunStatus.COMPLETED,
                    finish_reason=finish_reason,
                    lease_token=lease_token,
                    usage=usage,
                    provider_request_id=provider_request_id,
                    model_calls=model_calls,
                    tool_calls=tool_calls,
                )
                return {"status": final.status, "run_id": str(run_id)}
            except RunExecutionCancelled:
                with suppress(Exception):
                    await reasoning_buffer.close()
                with suppress(Exception):
                    await text_buffer.close()
                with suppress(Exception):
                    await sync_to_async(converge_cancelled_tool_calls, thread_sensitive=True)(run_id)
                final = await sync_to_async(StreamWriter.finish, thread_sensitive=True)(
                    run_id=run_id, status=RunStatus.CANCELLED, lease_token=lease_token,
                )
                return {"status": final.status, "run_id": str(run_id)}
            except RunLeaseLost:
                return {"status": "lease_lost", "run_id": str(run_id)}
            except Exception as exc:
                if visible or tool_calls > 0 or attempt + 1 >= attempts:
                    with suppress(Exception):
                        await reasoning_buffer.close()
                    with suppress(Exception):
                        await text_buffer.close()
                    with suppress(Exception):
                        await sync_to_async(converge_cancelled_tool_calls, thread_sensitive=True)(run_id)
                    error = adapt_error(exc)
                    status = RunStatus.INTERRUPTED if visible else RunStatus.FAILED
                    final = await sync_to_async(StreamWriter.finish, thread_sensitive=True)(
                        run_id=run_id, status=status, finish_reason="error", error_code=error.code,
                        error_message=error.message, retryable=error.retryable, lease_token=lease_token,
                        usage=usage, provider_request_id=provider_request_id,
                    )
                    return {"status": final.status, "run_id": str(run_id)}
                await asyncio.sleep(min(2 ** attempt, 4))
                await ensure_running()
    except Exception as exc:
        error = adapt_error(exc)
        try:
            final = await sync_to_async(StreamWriter.finish, thread_sensitive=True)(
                run_id=run_id, status=RunStatus.FAILED, finish_reason="error",
                error_code=error.code, error_message=error.message, retryable=error.retryable, lease_token=lease_token,
            )
            return {"status": final.status, "run_id": str(run_id)}
        except RunLeaseLost:
            return {"status": "lease_lost", "run_id": str(run_id)}


def _save_route(run_id, route):
    from chat_sync.ai_models import ChatRun
    ChatRun.objects.filter(pk=run_id).update(provider=route.provider, model=route.model, model_config_version=route.config_version)


@shared_task(bind=True, name="chat_sync.ai_tasks.run_tasks.resume_chat_run", autoretry_for=(), max_retries=0)
def resume_chat_run(self, run_id: str, interaction_id: str = "", expected_generation: int | None = None, request_id: str = ""):
    """Resume the same Run after an Interaction response has committed."""
    return run_chat(run_id, expected_generation=expected_generation, request_id=request_id)
