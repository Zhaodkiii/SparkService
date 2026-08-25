from __future__ import annotations

from typing import Any, Iterable

from django.db import transaction
from django.utils import timezone

from chat_sync.ai_models import ChatDeferredToolState, ChatRun
from chat_sync.ai_runtime.capabilities import build_capability_registry
from chat_sync.ai_runtime.tools.deferred import short_catalog, validate_load_names
from chat_sync.ai_runtime.tools.registry import build_server_tool_registry
from common.exceptions import APIError


class DeferredToolService:
    """Owns per-thread deferred tool state and Run-scoped authorization."""

    @staticmethod
    def _error(message: str, code: int = 40096, status: int = 400, details: dict[str, Any] | None = None):
        return APIError(message, code=code, status_code=status, details=details)

    @classmethod
    def _run(cls, *, user_id: int, run_id) -> ChatRun:
        run = ChatRun.objects.select_related("thread").filter(id=run_id, user_id=user_id).first()
        if run is None:
            raise cls._error("chat_run_not_found", 40491, 404)
        return run

    @classmethod
    def catalog(cls, *, user_id: int, thread_id, run_id=None) -> dict[str, Any]:
        run = cls._run(user_id=user_id, run_id=run_id) if run_id else None
        if run is not None and str(run.thread_id) != str(thread_id):
            raise cls._error("chat_thread_run_mismatch", 40994, 409)
        if run is None:
            from chat_sync.models import ChatThread

            if not ChatThread.objects.filter(id=thread_id, user_id=user_id, is_deleted=False).exists():
                raise cls._error("chat_thread_not_found", 40491, 404)
        registry = build_server_tool_registry()
        loaded = set(
            ChatDeferredToolState.objects.filter(thread_id=thread_id, loaded_at__isnull=False, revoked_at__isnull=True)
            .values_list("tool_name", flat=True)
        )
        return {
            "tools": short_catalog(registry),
            "loaded": sorted(loaded),
            "capability": {"id": run.capability, "version": run.capability_version} if run else None,
        }

    @classmethod
    @transaction.atomic
    def load(cls, *, user_id: int, thread_id, run_id, names: Iterable[str]) -> dict[str, Any]:
        run = cls._run(user_id=user_id, run_id=run_id)
        run = ChatRun.objects.select_for_update().select_related("thread").get(pk=run.pk)
        if str(run.thread_id) != str(thread_id):
            raise cls._error("chat_thread_run_mismatch", 40994, 409)
        if run.is_terminal:
            raise cls._error("chat_run_not_active", 40995, 409)
        try:
            names = validate_load_names(names)
        except ValueError as exc:
            raise cls._error("chat_deferred_tool_names_invalid", details={"reason": str(exc)}) from exc
        registry = build_server_tool_registry()
        capability = build_capability_registry().require(run.capability, run.capability_version)
        client_snapshot = (run.request_snapshot or {}).get("client") or {}
        client_names = {
            str(item.get("name") if isinstance(item, dict) else item)
            for item in (client_snapshot.get("client_tools") or [])
        }
        allowed = set(capability.owned_tools) | set(registry.list_names())
        unknown = [name for name in names if name not in allowed or registry.get(name) is None]
        if unknown:
            raise cls._error("chat_deferred_tool_not_available", details={"names": unknown})
        for name in names:
            entry = registry.get(name)
            if entry.policy.target == "client":
                if str(client_snapshot.get("platform") or "") not in entry.policy.supported_platforms:
                    raise cls._error("chat_deferred_tool_platform_unsupported", details={"name": name})
                if name not in client_names:
                    raise cls._error("chat_deferred_tool_client_capability_missing", details={"name": name})
            if "member" in entry.policy.required_context and run.thread.member_id is None:
                raise cls._error("chat_deferred_tool_member_required", details={"name": name})
        now = timezone.now()
        states = []
        for name in names:
            entry = registry.get(name)
            state, _ = ChatDeferredToolState.objects.select_for_update().get_or_create(
                thread_id=thread_id,
                provider_key="server",
                tool_name=name,
                defaults={"schema_version": entry.policy.version},
            )
            state.schema_version = entry.policy.version
            state.schema_hash = entry.schema_hash
            state.capability = run.capability
            state.capability_version = run.capability_version
            state.loaded_at = now
            state.revoked_at = None
            state.revoke_reason = ""
            state.last_loaded_run = run
            state.save()
            states.append(state)
        for name in names:
            from chat_sync.ai_services.run_service import RunService

            RunService._append_event_locked(
                run=run,
                event_type="tool.deferred.loaded",
                payload={"tool_name": name, "provider_key": "server", "schema_hash": registry.get(name).schema_hash},
            )
        return {
            "loaded": names,
            "schemas": [registry.get(name).schema for name in names],
            "states": [cls.serialize(state) for state in states],
        }

    @classmethod
    @transaction.atomic
    def revoke(cls, *, user_id: int, thread_id, names: Iterable[str], reason: str = "user_revoked") -> list[dict[str, Any]]:
        try:
            normalized = validate_load_names(names)
        except ValueError as exc:
            raise cls._error("chat_deferred_tool_names_invalid", details={"reason": str(exc)}) from exc
        states = list(
            ChatDeferredToolState.objects.select_for_update().filter(
                thread__id=thread_id, thread__user_id=user_id, tool_name__in=normalized
            )
        )
        now = timezone.now()
        for state in states:
            state.revoked_at = now
            state.revoke_reason = str(reason or "user_revoked")[:128]
            state.save(update_fields=["revoked_at", "revoke_reason", "updated_at"])
        return [cls.serialize(state) for state in states]

    @staticmethod
    def active_names(*, thread_id, capability: str = "", capability_version: str = "") -> list[str]:
        query = ChatDeferredToolState.objects.filter(thread_id=thread_id, loaded_at__isnull=False, revoked_at__isnull=True)
        if capability:
            query = query.filter(capability=capability, capability_version=capability_version)
        return list(query.values_list("tool_name", flat=True))

    @staticmethod
    def serialize(state: ChatDeferredToolState) -> dict[str, Any]:
        return {
            "provider_key": state.provider_key,
            "tool_name": state.tool_name,
            "schema_version": state.schema_version,
            "schema_hash": state.schema_hash,
            "capability": state.capability,
            "capability_version": state.capability_version,
            "loaded_at": state.loaded_at.isoformat() if state.loaded_at else None,
            "revoked_at": state.revoked_at.isoformat() if state.revoked_at else None,
            "revoke_reason": state.revoke_reason,
        }


__all__ = ["DeferredToolService"]
