from __future__ import annotations

import hashlib
import json
import logging
import math
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from chat_sync.ai_models import (
    ChatPendingInteraction,
    ChatRun,
    ChatThreadRunLock,
    ChatToolCall,
    RunStatus,
)
from chat_sync.ai_models.run import assert_run_transition
from chat_sync.ai_runtime.tools.observability import emit_metric
from chat_sync.ai_services.run_service import RunService
from chat_sync.contracts import (
    KIND_SEARCH_SUMMARY,
    KIND_TOOL_QUESTION_CARDS,
    NODE_ROLE_TOOL_PRESENTATION,
    search_summary_payload,
    tool_question_cards_payload,
)
from chat_sync.models import ChatMessageBlock
from common.exceptions import APIError

logger = logging.getLogger("chat_sync.ai.interaction")

ASK_USER_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class InteractionCommandResult:
    interaction: ChatPendingInteraction
    run: ChatRun
    replayed: bool = False


class PendingInteractionService:
    ASK_USER_TTL = 24 * 60 * 60
    CLIENT_TOOL_TTL = 10 * 60
    CLAIM_TTL = 90

    @staticmethod
    def _error(message: str, code: int, status: int, details: dict[str, Any] | None = None) -> APIError:
        return APIError(message, code=code, status_code=status, details=details)

    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    @classmethod
    def _hash(cls, value: Any) -> str:
        return hashlib.sha256(cls._canonical(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _summary(value: Any, limit: int = 512) -> str:
        text = value if isinstance(value, str) else PendingInteractionService._canonical(value)
        return text[:limit]

    @staticmethod
    def _question_ids(request_schema: dict[str, Any] | None) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        questions = (request_schema or {}).get("questions") if isinstance(request_schema, dict) else None
        if not isinstance(questions, list):
            return ids
        for item in questions:
            if not isinstance(item, dict):
                continue
            question_id = str(item.get("id") or "").strip()
            if not question_id or question_id in seen:
                continue
            seen.add(question_id)
            ids.append(question_id)
        return ids

    @classmethod
    def _model_call_id(cls, interaction: ChatPendingInteraction) -> str:
        return str(interaction.tool_call.tool_call_id)

    @classmethod
    def serialize(cls, interaction: ChatPendingInteraction, *, include_response: bool = False) -> dict[str, Any]:
        data = {
            "run_id": str(interaction.run_id),
            "interaction_id": str(interaction.public_id),
            "interaction_key": interaction.interaction_key,
            "kind": interaction.kind,
            "status": interaction.status,
            "tool_call_id": cls._model_call_id(interaction),
            "tool_name": interaction.tool_call.tool_name,
            "tool_version": interaction.tool_version or interaction.tool_call.tool_version or "v1",
            "schema_version": interaction.schema_version,
            "question_ids": cls._question_ids(interaction.request_schema),
            "request": interaction.request_schema,
            "expires_at": interaction.expires_at.isoformat() if interaction.expires_at else None,
            "required_platform": interaction.required_platform,
            "required_capability": interaction.required_capability,
            "claim_expires_at": interaction.claim_expires_at.isoformat() if interaction.claim_expires_at else None,
            "result_summary": interaction.result_summary,
            "error_code": interaction.last_error_code,
        }
        if include_response and interaction.response is not None:
            data["response"] = interaction.response
        return data

    @classmethod
    def _safe_answers_preview(cls, response: dict[str, Any] | None) -> list[dict[str, Any]] | None:
        if not isinstance(response, dict):
            return None
        answers = response.get("answers")
        if not isinstance(answers, list):
            return None
        preview: list[dict[str, Any]] = []
        for item in answers:
            if not isinstance(item, dict):
                continue
            labels = item.get("selected_labels") if isinstance(item.get("selected_labels"), list) else []
            free_text = str(item.get("free_text") or "")
            preview.append(
                {
                    "question_id": str(item.get("question_id") or ""),
                    "selected_labels": [str(label) for label in labels],
                    "has_free_text": bool(free_text.strip()),
                }
            )
        return preview

    @classmethod
    def _block_kind_for(cls, kind: str) -> str:
        if kind == ChatPendingInteraction.Kind.ASK_USER:
            return KIND_TOOL_QUESTION_CARDS
        return KIND_SEARCH_SUMMARY

    @classmethod
    def _question_cards_payload(
        cls,
        interaction: ChatPendingInteraction,
        *,
        status: str,
        answers: list[dict[str, Any]] | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        return tool_question_cards_payload(
            run_id=str(interaction.run_id),
            interaction_id=str(interaction.public_id),
            interaction_key=interaction.interaction_key,
            tool_call_id=cls._model_call_id(interaction),
            tool_name=interaction.tool_call.tool_name,
            tool_version=interaction.tool_version or interaction.tool_call.tool_version or "v1",
            schema_version=interaction.schema_version,
            status=status,
            question_ids=cls._question_ids(interaction.request_schema),
            request=interaction.request_schema if isinstance(interaction.request_schema, dict) else {},
            expires_at=interaction.expires_at.isoformat() if interaction.expires_at else None,
            answers=answers,
            error_code=error_code,
        )

    @classmethod
    def _client_waiting_payload(cls, interaction: ChatPendingInteraction) -> dict[str, Any]:
        return search_summary_payload(
            provider_name=interaction.tool_call.tool_name,
            query="等待客户端工具",
        )

    @classmethod
    def _payload_for_status(
        cls,
        interaction: ChatPendingInteraction,
        *,
        status: str,
        answers: list[dict[str, Any]] | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        if interaction.kind == ChatPendingInteraction.Kind.ASK_USER:
            return cls._question_cards_payload(interaction, status=status, answers=answers, error_code=error_code)
        if status == ChatPendingInteraction.Status.PENDING:
            return cls._client_waiting_payload(interaction)
        return search_summary_payload(
            provider_name=interaction.tool_call.tool_name,
            query=interaction.result_summary or "客户端工具已结束",
        )

    @staticmethod
    def _block_event_payload(*, run: ChatRun, block: ChatMessageBlock) -> dict[str, Any]:
        payload = dict(block.payload or {})
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

    @classmethod
    def _upsert_interaction_block(
        cls,
        *,
        run: ChatRun,
        interaction: ChatPendingInteraction,
        block_status: str,
        payload: dict[str, Any],
        now,
    ) -> ChatMessageBlock | None:
        if run.assistant_message is None:
            return None
        tool_call_id = cls._model_call_id(interaction)
        block_kind = cls._block_kind_for(interaction.kind)
        block = run.assistant_message.blocks.filter(tool_call_id=tool_call_id, kind=block_kind).first()
        created = False
        if block is None:
            block = ChatMessageBlock.objects.create(
                user=run.user,
                thread=run.thread,
                message=run.assistant_message,
                kind=block_kind,
                status=block_status,
                revision=1,
                order_key=2100 + interaction.tool_call.call_index,
                tool_call_id=tool_call_id,
                node_role=NODE_ROLE_TOOL_PRESENTATION,
                payload=payload,
                created_at=now,
                updated_at=now,
            )
            created = True
        else:
            block.status = block_status
            block.revision += 1
            block.payload = payload
            block.updated_at = now
            block.save(update_fields=["status", "revision", "payload", "updated_at", "server_updated_at"])
        RunService._append_event_locked(
            run=run,
            event_type="block.created" if created else "block.updated",
            payload=cls._block_event_payload(run=run, block=block),
        )
        return block

    @classmethod
    def _get_locked(cls, *, user_id: int, public_id) -> ChatPendingInteraction:
        interaction = (
            ChatPendingInteraction.objects.select_for_update()
            .select_related("run", "tool_call", "run__thread", "run__assistant_message")
            .filter(public_id=public_id, run__user_id=user_id)
            .first()
        )
        if interaction is None:
            raise cls._error("chat_interaction_not_found", 40494, 404)
        return interaction

    @classmethod
    def get_for_read(cls, *, user_id: int, public_id) -> ChatPendingInteraction:
        interaction = (
            ChatPendingInteraction.objects.select_related("run", "tool_call")
            .filter(public_id=public_id, run__user_id=user_id)
            .first()
        )
        if interaction is None:
            raise cls._error("chat_interaction_not_found", 40494, 404)
        return interaction

    @classmethod
    def list_pending(cls, *, user_id: int, run_id) -> list[ChatPendingInteraction]:
        return list(
            ChatPendingInteraction.objects.select_related("run", "tool_call")
            .filter(run_id=run_id, run__user_id=user_id, status__in=[ChatPendingInteraction.Status.PENDING, ChatPendingInteraction.Status.CLAIMED])
            .order_by("created_at", "id")
        )

    @classmethod
    @transaction.atomic
    def pause_for_tool(
        cls,
        *,
        run_id,
        tool_call_id: str,
        kind: str,
        request_schema: dict[str, Any],
        required_platform: str = "",
        required_capability: str = "",
        tool_version: str = "v1",
        expires_in_seconds: int | None = None,
        lease_token=None,
    ) -> ChatPendingInteraction:
        run = ChatRun.objects.select_for_update().select_related("thread", "assistant_message").get(pk=run_id)
        lock = ChatThreadRunLock.objects.select_for_update().get(thread=run.thread)
        if run.status != RunStatus.RUNNING:
            raise cls._error("chat_run_not_running", 40995, 409)
        if lease_token is not None and run.lease_token != lease_token:
            raise cls._error("chat_run_lease_stale", 40996, 409)
        tool_call = ChatToolCall.objects.select_for_update().filter(run=run, tool_call_id=tool_call_id).first()
        if tool_call is None:
            raise cls._error("chat_tool_call_not_found", 40495, 404)
        if kind not in {ChatPendingInteraction.Kind.ASK_USER, ChatPendingInteraction.Kind.CLIENT_TOOL}:
            raise cls._error("chat_interaction_kind_invalid", 42294, 422)
        if not isinstance(request_schema, dict) or not request_schema:
            raise cls._error("chat_interaction_request_invalid", 42295, 422)
        interaction_key = f"run:{run.id}:tool:{tool_call_id}:stage:0"
        request_hash = cls._hash(request_schema)
        schema_version = ASK_USER_SCHEMA_VERSION if kind == ChatPendingInteraction.Kind.ASK_USER else 1
        interaction, created = ChatPendingInteraction.objects.get_or_create(
            interaction_key=interaction_key,
            defaults={
                "run": run,
                "tool_call": tool_call,
                "kind": kind,
                "schema_version": schema_version,
                "request_schema": request_schema,
                "request_hash": request_hash,
                "required_platform": required_platform[:32],
                "required_capability": required_capability[:64],
                "tool_version": tool_version[:64],
                "expires_at": timezone.now() + timedelta(seconds=max(1, int(expires_in_seconds or (cls.ASK_USER_TTL if kind == "ask_user" else cls.CLIENT_TOOL_TTL)))),
                "max_attempts": 3,
            },
        )
        if not created:
            if interaction.request_hash != request_hash:
                raise cls._error("chat_interaction_request_conflict", 40997, 409)
            return interaction
        waiting_status = ChatToolCall.Status.WAITING_FOR_USER if kind == ChatPendingInteraction.Kind.ASK_USER else ChatToolCall.Status.WAITING_FOR_CLIENT
        tool_call.status = waiting_status
        tool_call.started_at = tool_call.started_at or timezone.now()
        tool_call.save(update_fields=["status", "started_at", "updated_at"])
        target_run_status = RunStatus.WAITING_FOR_USER_INPUT if kind == ChatPendingInteraction.Kind.ASK_USER else RunStatus.WAITING_FOR_CLIENT_TOOL
        assert_run_transition(run.status, target_run_status)
        run.status = target_run_status
        run.lease_owner = ""
        run.lease_token = None
        run.lease_expires_at = None
        run.save(update_fields=["status", "lease_owner", "lease_token", "lease_expires_at", "updated_at"])
        now = timezone.now()
        cls._upsert_interaction_block(
            run=run,
            interaction=interaction,
            block_status=ChatMessageBlock.Status.PENDING,
            payload=cls._payload_for_status(interaction, status=ChatPendingInteraction.Status.PENDING),
            now=now,
        )
        RunService._append_event_locked(run=run, event_type="interaction.requested", payload={"interaction": cls.serialize(interaction)})
        RunService._append_event_locked(
            run=run,
            event_type="run.waiting",
            payload={"status": run.status, "interaction_id": str(interaction.public_id)},
        )
        if lock.active_run_id != run.id:
            raise cls._error("chat_run_lock_lost", 40998, 409)
        emit_metric(
            "chat_interaction_total",
            kind=kind,
            status=ChatPendingInteraction.Status.PENDING,
            tool=tool_call.tool_name,
            run_id=run.id,
            interaction_id=interaction.public_id,
            tool_call_id=tool_call.tool_call_id,
        )
        logger.info(
            "interaction.paused run_id=%s interaction_id=%s tool_call_id=%s kind=%s",
            run.id,
            interaction.public_id,
            tool_call.tool_call_id,
            kind,
        )
        return interaction

    @classmethod
    def _validate_ask_answer(cls, interaction: ChatPendingInteraction, response: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if str(response.get("run_id") or "") and str(response.get("run_id")) != str(interaction.run_id):
            raise cls._error("chat_interaction_response_invalid", 42296, 422, {"field": "run_id"})
        if str(response.get("interaction_key") or "") and str(response.get("interaction_key")) != interaction.interaction_key:
            raise cls._error("chat_interaction_response_invalid", 42296, 422, {"field": "interaction_key"})
        if response.get("schema_version") is not None:
            try:
                submitted_version = int(response.get("schema_version"))
            except (TypeError, ValueError):
                raise cls._error("chat_interaction_response_invalid", 42296, 422, {"field": "schema_version"})
            if submitted_version != int(interaction.schema_version):
                raise cls._error("chat_interaction_response_invalid", 42296, 422, {"field": "schema_version"})
        resolution = str(response.get("resolution") or "answered")
        if resolution not in {"answered", "skipped", "refused"}:
            raise cls._error("chat_interaction_response_invalid", 42296, 422)
        if resolution != "answered":
            return resolution, {"resolution": resolution, "reason": str(response.get("reason") or "")[:128]}
        allowed_ids = cls._question_ids(interaction.request_schema)
        allowed_set = set(allowed_ids)
        submitted_ids = response.get("question_ids")
        if submitted_ids is not None:
            if not isinstance(submitted_ids, list) or len(submitted_ids) != len(set(str(item) for item in submitted_ids)):
                raise cls._error("chat_interaction_response_invalid", 42296, 422, {"field": "question_ids"})
            if not set(str(item) for item in submitted_ids).issubset(allowed_set):
                raise cls._error("chat_interaction_response_invalid", 42296, 422, {"field": "question_ids"})
        questions = interaction.request_schema.get("questions") or []
        by_id = {str(item.get("id")): item for item in questions if isinstance(item, dict)}
        answers = response.get("answers")
        if not isinstance(answers, list) or not answers:
            raise cls._error("chat_interaction_response_invalid", 42296, 422, {"field": "answers"})
        normalized = []
        seen = set()
        for answer in answers:
            if not isinstance(answer, dict):
                raise cls._error("chat_interaction_response_invalid", 42296, 422)
            question_id = str(answer.get("question_id") or "")
            question = by_id.get(question_id)
            if not question or question_id in seen or question_id not in allowed_set:
                raise cls._error("chat_interaction_response_invalid", 42296, 422, {"question_id": question_id})
            seen.add(question_id)
            indexes = answer.get("selected_option_indexes")
            labels = answer.get("selected_labels")
            if indexes is None:
                indexes = []
            if labels is None:
                labels = []
            if not isinstance(indexes, list) or not isinstance(labels, list) or len(indexes) != len(labels):
                raise cls._error("chat_interaction_response_invalid", 42296, 422, {"question_id": question_id})
            if (indexes and not labels) or (labels and not indexes):
                raise cls._error("chat_interaction_response_invalid", 42296, 422, {"question_id": question_id})
            options = question.get("options") or []
            selected_labels = []
            for index, label in zip(indexes, labels):
                if not isinstance(index, int) or index < 0 or index >= len(options):
                    raise cls._error("chat_interaction_response_invalid", 42296, 422, {"question_id": question_id})
                expected = options[index].get("label") if isinstance(options[index], dict) else str(options[index])
                if str(label) != str(expected):
                    raise cls._error("chat_interaction_response_invalid", 42296, 422, {"question_id": question_id})
                selected_labels.append(str(expected))
            if not bool(question.get("multi_select")) and len(indexes) > 1:
                raise cls._error("chat_interaction_response_invalid", 42296, 422, {"question_id": question_id})
            free_text = str(answer.get("free_text") or "")
            if free_text and not bool(question.get("allow_free_text", True)):
                raise cls._error("chat_interaction_response_invalid", 42296, 422, {"question_id": question_id})
            if not indexes and not free_text.strip():
                raise cls._error("chat_interaction_response_invalid", 42296, 422, {"question_id": question_id})
            normalized.append({"question_id": question_id, "selected_option_indexes": indexes, "selected_labels": selected_labels, "free_text": free_text[:2000]})
        return resolution, {"resolution": resolution, "answers": normalized}

    @classmethod
    def _validate_client_response(cls, interaction: ChatPendingInteraction, response: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
        if not isinstance(response, dict):
            raise cls._error("chat_interaction_response_invalid", 42296, 422)
        resolution = str(response.get("resolution") or "completed")
        if resolution in {"refused", "skipped"}:
            return "refused", {"resolution": resolution, "reason": str(response.get("reason") or "")[:128]}, str(response.get("reason") or "client_refused")[:64]
        if resolution != "completed" or str(response.get("request_hash") or "") != interaction.request_hash:
            raise cls._error("chat_interaction_response_invalid", 42296, 422, {"reason": "request_hash_or_resolution"})
        result = response.get("result")
        if not isinstance(result, dict):
            raise cls._error("chat_interaction_response_invalid", 42296, 422, {"field": "result"})
        if len(cls._canonical(result).encode("utf-8")) > 64 * 1024:
            raise cls._error("chat_interaction_response_invalid", 42296, 422, {"reason": "result_too_large"})
        if interaction.tool_call.tool_name == "get_current_location":
            try:
                latitude, longitude = float(result["latitude"]), float(result["longitude"])
                accuracy = float(result["horizontal_accuracy_m"])
            except (KeyError, TypeError, ValueError):
                raise cls._error("chat_interaction_response_invalid", 42296, 422)
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180 and 0 < accuracy <= 10000):
                raise cls._error("chat_interaction_response_invalid", 42296, 422)
            if not result.get("captured_at"):
                raise cls._error("chat_interaction_response_invalid", 42296, 422, {"field": "captured_at"})
        elif interaction.tool_call.tool_name.startswith("fetch_"):
            aggregates = result.get("aggregates", result.get("days", []))
            if aggregates is not None:
                if not isinstance(aggregates, list) or len(aggregates) > 31:
                    raise cls._error("chat_interaction_response_invalid", 42296, 422, {"field": "aggregates"})
                for item in aggregates:
                    if not isinstance(item, dict):
                        raise cls._error("chat_interaction_response_invalid", 42296, 422)
                    for value in item.values():
                        if isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(float(value)):
                            raise cls._error("chat_interaction_response_invalid", 42296, 422)
            samples = result.get("samples")
            if samples is not None and (not isinstance(samples, list) or len(samples) > 100):
                raise cls._error("chat_interaction_response_invalid", 42296, 422, {"field": "samples"})
        sanitized = {"resolution": "completed", "result": result, "execution": response.get("execution") or {}}
        return "resolved", sanitized, ""

    @classmethod
    def _append_tool_observation(cls, *, run: ChatRun, tool: ChatToolCall, content: str) -> None:
        checkpoint = None
        try:
            checkpoint = run.agent_checkpoint
        except Exception:
            checkpoint = None
        if checkpoint is None:
            return
        transcript = list(checkpoint.transcript or [])
        already = any(
            isinstance(item, dict)
            and item.get("role") == "tool"
            and item.get("tool_call_id") == tool.tool_call_id
            for item in transcript
        )
        if already:
            return
        transcript.append({"role": "tool", "tool_call_id": tool.tool_call_id, "name": tool.tool_name, "content": content})
        checkpoint.transcript = transcript[-64:]
        checkpoint.revision += 1
        checkpoint.next_round_index = max(checkpoint.next_round_index, tool.round_index + 1)
        checkpoint.save(update_fields=["transcript", "revision", "next_round_index", "updated_at"])

    @classmethod
    @transaction.atomic
    def resolve(
        cls,
        *,
        user_id: int,
        public_id,
        response: dict[str, Any],
        idempotency_key: str,
        device_id: str = "",
        claim_token: str = "",
    ) -> InteractionCommandResult:
        if not idempotency_key or len(idempotency_key) > 128:
            raise cls._error("chat_interaction_idempotency_required", 40097, 400)
        interaction = cls._get_locked(user_id=user_id, public_id=public_id)
        run = ChatRun.objects.select_for_update().select_related("thread", "assistant_message").get(pk=interaction.run_id)
        lock = ChatThreadRunLock.objects.select_for_update().get(thread=run.thread)
        if interaction.response_idempotency_key == idempotency_key and interaction.response is not None:
            if interaction.response_hash != cls._hash(response):
                emit_metric("chat_interaction_response_conflict_total", kind=interaction.kind, reason="idempotency")
                raise cls._error("chat_interaction_idempotency_conflict", 40997, 409)
            emit_metric("chat_interaction_resume_total", outcome="replayed", kind=interaction.kind)
            return InteractionCommandResult(interaction, run, replayed=True)
        if interaction.status not in {ChatPendingInteraction.Status.PENDING, ChatPendingInteraction.Status.CLAIMED}:
            emit_metric("chat_interaction_response_conflict_total", kind=interaction.kind, reason="already_resolved")
            raise cls._error("chat_interaction_already_resolved", 40998, 409)
        if interaction.expires_at and interaction.expires_at <= timezone.now():
            raise cls._error("chat_interaction_expired", 41094, 410)
        if run.status not in {RunStatus.WAITING_FOR_USER_INPUT, RunStatus.WAITING_FOR_CLIENT_TOOL}:
            raise cls._error("chat_run_not_waiting_for_interaction", 40999, 409)
        if interaction.kind == ChatPendingInteraction.Kind.CLIENT_TOOL:
            if not claim_token or not secrets.compare_digest(interaction.claim_token_hash, cls._hash(claim_token)):
                raise cls._error("chat_interaction_claim_invalid", 40996, 409)
            if interaction.claim_expires_at and interaction.claim_expires_at <= timezone.now():
                raise cls._error("chat_interaction_claim_invalid", 40996, 409)
            resolution, normalized, reason = cls._validate_client_response(interaction, response)
        else:
            resolution, normalized = cls._validate_ask_answer(interaction, response)
            reason = "" if resolution == "answered" else str(normalized.get("reason") or "")[:64]
        response_hash = cls._hash(response)
        now = timezone.now()
        interaction.response = normalized
        interaction.response_hash = response_hash
        interaction.response_idempotency_key = idempotency_key
        interaction.responded_by_device = device_id[:128]
        interaction.response_received_at = now
        interaction.resolved_at = now
        interaction.status = ChatPendingInteraction.Status.RESOLVED if resolution in {"answered", "resolved"} else ChatPendingInteraction.Status.REFUSED
        interaction.last_error_code = reason
        interaction.result_summary = cls._summary(normalized)
        interaction.claim_token_hash = ""
        interaction.claim_expires_at = None
        interaction.save()
        tool = ChatToolCall.objects.select_for_update().get(pk=interaction.tool_call_id)
        tool.status = ChatToolCall.Status.COMPLETED
        tool.result_content = cls._summary(normalized, 8000)
        tool.result_summary = cls._summary(normalized)
        tool.result_metadata = {"resolution": resolution, "interaction_id": str(interaction.public_id)}
        tool.error_code = reason
        tool.finished_at = now
        tool.save(update_fields=["status", "result_content", "result_summary", "result_metadata", "error_code", "finished_at", "updated_at"])
        cls._upsert_interaction_block(
            run=run,
            interaction=interaction,
            block_status=ChatMessageBlock.Status.READY if interaction.status == ChatPendingInteraction.Status.RESOLVED else ChatMessageBlock.Status.FAILED,
            payload=cls._payload_for_status(
                interaction,
                status=interaction.status,
                answers=cls._safe_answers_preview(normalized),
                error_code=reason or None,
            ),
            now=now,
        )
        cls._append_tool_observation(run=run, tool=tool, content=interaction.result_summary)
        assert_run_transition(run.status, RunStatus.QUEUED)
        run.status = RunStatus.QUEUED
        lock.generation += 1
        lock.save(update_fields=["generation", "updated_at"])
        run.save(update_fields=["status", "updated_at"])
        event_type = "interaction.resolved" if resolution in {"answered", "resolved"} else "interaction.refused"
        RunService._append_event_locked(
            run=run,
            event_type=event_type,
            payload={"interaction_id": str(interaction.public_id), "resolution": resolution, "reason_code": reason, "interaction": cls.serialize(interaction)},
        )
        RunService._append_event_locked(run=run, event_type="run.resumed", payload={"interaction_id": str(interaction.public_id), "generation": lock.generation})
        RunService._append_event_locked(run=run, event_type="run.queued", payload={"status": RunStatus.QUEUED, "queue": "chat.ai", "resume": True})
        from chat_sync.ai_tasks.run_tasks import resume_chat_run
        generation = lock.generation
        transaction.on_commit(lambda: resume_chat_run.delay(str(run.id), str(interaction.public_id), expected_generation=generation), robust=True)
        emit_metric("chat_interaction_total", kind=interaction.kind, status=interaction.status, tool=tool.tool_name)
        emit_metric("chat_interaction_resume_total", outcome="accepted", kind=interaction.kind)
        wait_started = interaction.created_at or now
        emit_metric(
            "chat_interaction_wait_seconds",
            kind=interaction.kind,
            status=interaction.status,
            seconds=round(max(0.0, (now - wait_started).total_seconds()), 3),
        )
        logger.info(
            "interaction.resolved run_id=%s interaction_id=%s tool_call_id=%s status=%s replayed=0",
            run.id,
            interaction.public_id,
            tool.tool_call_id,
            interaction.status,
        )
        return InteractionCommandResult(interaction, run, replayed=False)

    @classmethod
    @transaction.atomic
    def claim(cls, *, user_id: int, public_id, device_id: str, platform: str, version: str) -> tuple[ChatPendingInteraction, str]:
        if not device_id or not platform:
            raise cls._error("chat_client_tool_device_session_invalid", 40395, 403)
        from accounts.models import AccountDeviceSession, TrustedDevice

        if not TrustedDevice.objects.filter(user_id=user_id, device_id=device_id, platform=platform, is_revoked=False).exists() or not AccountDeviceSession.objects.filter(user_id=user_id, device_id=device_id, status=AccountDeviceSession.Status.ACTIVE).exists():
            raise cls._error("chat_client_tool_device_session_invalid", 40395, 403)
        interaction = cls._get_locked(user_id=user_id, public_id=public_id)
        if interaction.kind != ChatPendingInteraction.Kind.CLIENT_TOOL:
            raise cls._error("chat_interaction_claim_not_supported", 40995, 409)
        if interaction.required_platform and interaction.required_platform != platform:
            raise cls._error("chat_client_tool_platform_mismatch", 40394, 403)
        if interaction.status == ChatPendingInteraction.Status.CLAIMED and interaction.claim_expires_at and interaction.claim_expires_at > timezone.now():
            raise cls._error("chat_interaction_already_claimed", 40994, 409)
        if interaction.status not in {ChatPendingInteraction.Status.PENDING, ChatPendingInteraction.Status.CLAIMED}:
            raise cls._error("chat_interaction_already_resolved", 40998, 409)
        if interaction.expires_at and interaction.expires_at <= timezone.now():
            raise cls._error("chat_interaction_expired", 41094, 410)
        if interaction.attempt_count >= interaction.max_attempts:
            raise cls._error("chat_interaction_attempts_exceeded", 40995, 409)
        token = secrets.token_urlsafe(32)
        interaction.status = ChatPendingInteraction.Status.CLAIMED
        interaction.claimed_by_device = device_id[:255]
        interaction.claim_token_hash = cls._hash(token)
        interaction.claim_expires_at = timezone.now() + timedelta(seconds=cls.CLAIM_TTL)
        interaction.attempt_count += 1
        interaction.save(update_fields=["status", "claimed_by_device", "claim_token_hash", "claim_expires_at", "attempt_count", "updated_at"])
        run = ChatRun.objects.select_for_update().get(pk=interaction.run_id)
        RunService._append_event_locked(run=run, event_type="interaction.claimed", payload={"interaction_id": str(interaction.public_id), "platform": platform, "claim_expires_at": interaction.claim_expires_at.isoformat()})
        return interaction, token

    @classmethod
    @transaction.atomic
    def heartbeat(cls, *, user_id: int, public_id, device_id: str, claim_token: str) -> ChatPendingInteraction:
        interaction = cls._get_locked(user_id=user_id, public_id=public_id)
        if interaction.status != ChatPendingInteraction.Status.CLAIMED or interaction.claimed_by_device != device_id or not secrets.compare_digest(interaction.claim_token_hash, cls._hash(claim_token)):
            raise cls._error("chat_interaction_claim_invalid", 40996, 409)
        if interaction.claim_expires_at and interaction.claim_expires_at <= timezone.now():
            raise cls._error("chat_interaction_claim_invalid", 40996, 409)
        interaction.claim_expires_at = timezone.now() + timedelta(seconds=cls.CLAIM_TTL)
        interaction.save(update_fields=["claim_expires_at", "updated_at"])
        return interaction

    @classmethod
    @transaction.atomic
    def cancel_for_run(cls, *, user_id: int, run_id) -> None:
        interactions = ChatPendingInteraction.objects.select_for_update().select_related("tool_call", "run", "run__assistant_message").filter(
            run_id=run_id,
            run__user_id=user_id,
            status__in=[ChatPendingInteraction.Status.PENDING, ChatPendingInteraction.Status.CLAIMED],
        )
        now = timezone.now()
        for interaction in interactions:
            interaction.status = ChatPendingInteraction.Status.CANCELLED
            interaction.resolved_at = now
            interaction.last_error_code = "run_cancelled"
            interaction.save(update_fields=["status", "resolved_at", "last_error_code", "updated_at"])
            run = ChatRun.objects.select_for_update().select_related("assistant_message").get(pk=interaction.run_id)
            cls._upsert_interaction_block(
                run=run,
                interaction=interaction,
                block_status=ChatMessageBlock.Status.FAILED,
                payload=cls._payload_for_status(interaction, status=ChatPendingInteraction.Status.CANCELLED, error_code="run_cancelled"),
                now=now,
            )
            RunService._append_event_locked(
                run=run,
                event_type="interaction.cancelled",
                payload={"interaction_id": str(interaction.public_id), "reason": "run_cancelled", "interaction": cls.serialize(interaction)},
            )
            emit_metric("chat_interaction_total", kind=interaction.kind, status="cancelled", tool=interaction.tool_call.tool_name)

    @classmethod
    def expire_due(cls, *, limit: int = 100) -> dict[str, int]:
        """Expire waiting interactions and enqueue one bounded timeout resume."""
        now = timezone.now()
        expired = resumed = reclaimed = 0
        ids = list(
            ChatPendingInteraction.objects.filter(
                status__in=[ChatPendingInteraction.Status.PENDING, ChatPendingInteraction.Status.CLAIMED],
                expires_at__isnull=False,
                expires_at__lte=now,
            ).values_list("public_id", flat=True)[:limit]
        )
        for public_id in ids:
            with transaction.atomic():
                interaction = ChatPendingInteraction.objects.select_for_update().select_related("tool_call").filter(public_id=public_id).first()
                if interaction is None or interaction.status not in {ChatPendingInteraction.Status.PENDING, ChatPendingInteraction.Status.CLAIMED}:
                    continue
                if interaction.kind == ChatPendingInteraction.Kind.CLIENT_TOOL and interaction.claim_expires_at and interaction.claim_expires_at > now:
                    continue
                run = ChatRun.objects.select_for_update().select_related("thread", "assistant_message").get(pk=interaction.run_id)
                if run.status not in {RunStatus.WAITING_FOR_USER_INPUT, RunStatus.WAITING_FOR_CLIENT_TOOL}:
                    interaction.status = ChatPendingInteraction.Status.EXPIRED
                    interaction.last_error_code = "run_not_waiting"
                    interaction.resolved_at = now
                    interaction.save(update_fields=["status", "last_error_code", "resolved_at", "updated_at"])
                    expired += 1
                    continue
                lock = ChatThreadRunLock.objects.select_for_update().get(thread=run.thread)
                interaction.status = ChatPendingInteraction.Status.EXPIRED
                interaction.resolved_at = now
                interaction.last_error_code = "interaction_expired"
                interaction.result_summary = "等待响应超时。"
                interaction.claim_token_hash = ""
                interaction.claim_expires_at = None
                interaction.save(update_fields=["status", "resolved_at", "last_error_code", "result_summary", "claim_token_hash", "claim_expires_at", "updated_at"])
                tool = ChatToolCall.objects.select_for_update().get(pk=interaction.tool_call_id)
                tool.status = ChatToolCall.Status.EXPIRED
                tool.result_content = interaction.result_summary
                tool.result_summary = interaction.result_summary
                tool.error_code = "chat_interaction_expired"
                tool.finished_at = now
                tool.save(update_fields=["status", "result_content", "result_summary", "error_code", "finished_at", "updated_at"])
                cls._append_tool_observation(run=run, tool=tool, content=interaction.result_summary)
                cls._upsert_interaction_block(
                    run=run,
                    interaction=interaction,
                    block_status=ChatMessageBlock.Status.FAILED,
                    payload=cls._payload_for_status(interaction, status=ChatPendingInteraction.Status.EXPIRED, error_code="interaction_expired"),
                    now=now,
                )
                assert_run_transition(run.status, RunStatus.QUEUED)
                run.status = RunStatus.QUEUED
                lock.generation += 1
                generation = lock.generation
                lock.save(update_fields=["generation", "updated_at"])
                run.save(update_fields=["status", "updated_at"])
                RunService._append_event_locked(
                    run=run,
                    event_type="interaction.expired",
                    payload={"interaction_id": str(interaction.public_id), "expired_at": now.isoformat(), "interaction": cls.serialize(interaction)},
                )
                RunService._append_event_locked(run=run, event_type="run.resumed", payload={"interaction_id": str(interaction.public_id), "generation": generation, "reason": "expired"})
                RunService._append_event_locked(run=run, event_type="run.queued", payload={"status": RunStatus.QUEUED, "queue": "chat.ai", "resume": True})
                from chat_sync.ai_tasks.run_tasks import resume_chat_run
                transaction.on_commit(lambda run_id=run.id, generation=generation, interaction_id=interaction.public_id: resume_chat_run.delay(str(run_id), str(interaction_id), expected_generation=generation), robust=True)
                expired += 1
                resumed += 1
                emit_metric("chat_interaction_total", kind=interaction.kind, status="expired", tool=tool.tool_name)
                emit_metric("chat_interaction_resume_total", outcome="expired", kind=interaction.kind)
                wait_started = interaction.created_at or now
                emit_metric(
                    "chat_interaction_wait_seconds",
                    kind=interaction.kind,
                    status="expired",
                    seconds=round(max(0.0, (now - wait_started).total_seconds()), 3),
                )
        claim_ids = list(
            ChatPendingInteraction.objects.filter(
                status=ChatPendingInteraction.Status.CLAIMED,
                claim_expires_at__isnull=False,
                claim_expires_at__lte=now,
                expires_at__gt=now,
            ).values_list("public_id", flat=True)[:limit]
        )
        for public_id in claim_ids:
            with transaction.atomic():
                interaction = ChatPendingInteraction.objects.select_for_update().filter(public_id=public_id, status=ChatPendingInteraction.Status.CLAIMED).first()
                if interaction is None:
                    continue
                interaction.status = ChatPendingInteraction.Status.PENDING
                interaction.claimed_by_device = ""
                interaction.claim_token_hash = ""
                interaction.claim_expires_at = None
                interaction.save(update_fields=["status", "claimed_by_device", "claim_token_hash", "claim_expires_at", "updated_at"])
                reclaimed += 1
        return {"expired": expired, "resumed": resumed, "reclaimed": reclaimed}


__all__ = ["ASK_USER_SCHEMA_VERSION", "InteractionCommandResult", "PendingInteractionService"]
