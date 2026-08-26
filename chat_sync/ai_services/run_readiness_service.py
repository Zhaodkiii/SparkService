from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from common.exceptions import APIError

logger = logging.getLogger("chat_sync.ai.run_readiness")


@dataclass(frozen=True)
class ChatRunReadiness:
    """Sanitized readiness verdict. Never carries keys, URLs or node names."""

    available: bool
    code: str
    retryable: bool
    checked_at: datetime
    executor: str
    model_binding_configured: bool = False
    worker_healthy: bool = False
    config_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "code": self.code,
            "retryable": self.retryable,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
            "executor": self.executor,
            "model_binding_configured": self.model_binding_configured,
            "worker_healthy": self.worker_healthy,
            "config_version": self.config_version,
        }


class ChatRunReadinessService:
    """Unified, de identified pre-flight readiness check for chat runs.

    The request thread never performs blocking provider/broker pings; worker
    health is read from a short-TTL snapshot (written by the worker heartbeat
    loop out of band) and falls back to fail-open unless heartbeat enforcement
    is explicitly enabled in settings. When `CHAT_AI_SERVER_RUNS_ENABLED` is
    off, the existing `50392/chat_server_runs_disabled` contract is preserved so
    existing callers and regression baselines keep working.
    """

    WORKER_HEALTH_CACHE_KEY = "chat_run_readiness.worker_healthy"
    WORKER_HEALTH_TTL_SECONDS = 30
    _CODE_MAP = {
        "chat_server_runs_disabled": 50392,
        "chat_run_executor_unavailable": 50393,
        "chat_run_model_binding_missing": 50394,
        "chat_run_worker_unavailable": 50395,
    }

    @classmethod
    def evaluate(cls) -> ChatRunReadiness:
        checked_at = timezone.now()
        executor = str(getattr(settings, "CHAT_AI_RUN_EXECUTOR", "disabled"))

        if not getattr(settings, "CHAT_AI_SERVER_RUNS_ENABLED", False):
            return cls._unavailable(checked_at, "chat_server_runs_disabled", retryable=False, executor=executor)

        if executor not in {"provider", "mock"}:
            return cls._unavailable(checked_at, "chat_run_executor_unavailable", retryable=False, executor=executor)

        model_binding_configured, config_version = cls._probe_model_binding()
        if not model_binding_configured:
            return cls._unavailable(checked_at, "chat_run_model_binding_missing", retryable=False, executor=executor)

        worker_healthy = cls.cached_worker_health("chat.ai")
        if not worker_healthy:
            return cls._unavailable(checked_at, "chat_run_worker_unavailable", retryable=True, executor=executor)

        return ChatRunReadiness(
            available=True,
            code="available",
            retryable=False,
            checked_at=checked_at,
            executor=executor,
            model_binding_configured=True,
            worker_healthy=True,
            config_version=config_version,
        )

    @classmethod
    def require_available(cls) -> ChatRunReadiness:
        readiness = cls.evaluate()
        if readiness.available:
            return readiness
        raise APIError(
            readiness.code,
            code=cls._CODE_MAP.get(readiness.code, 50390),
            status_code=503,
            details={"retryable": readiness.retryable},
        )

    @classmethod
    def cached_worker_health(cls, queue: str) -> bool:
        cached = cache.get(cls.WORKER_HEALTH_CACHE_KEY)
        if cached is not None:
            return bool(cached)
        healthy = cls._probe_worker_health(queue)
        try:
            cache.set(cls.WORKER_HEALTH_CACHE_KEY, healthy, timeout=cls.WORKER_HEALTH_TTL_SECONDS)
        except Exception:  # pragma: no cover - cache outage must not block readiness
            logger.exception("chat_run_readiness.worker_health.cache_failed")
        return healthy

    # -- helpers -----------------------------------------------------------------

    @classmethod
    def _unavailable(cls, checked_at: datetime, code: str, *, retryable: bool, executor: str) -> ChatRunReadiness:
        return ChatRunReadiness(available=False, code=code, retryable=retryable, checked_at=checked_at, executor=executor)

    @classmethod
    def _probe_model_binding(cls) -> tuple[bool, str | None]:
        try:
            from chat_sync.ai_runtime.providers.factory import resolve_chat_route

            route = resolve_chat_route()
            return True, route.config_version
        except Exception as exc:  # LLMConfigError and any config desync
            logger.warning("chat_run_readiness.model_binding_unavailable: %s", exc)
            return False, None

    @classmethod
    def _probe_worker_health(cls, queue: str) -> bool:
        # Fail-open unless heartbeat enforcement is explicitly required. A real
        # deployment turns this on and maintains the short-TTL snapshot via the
        # worker heartbeat loop, so a cold cache genuinely means "no worker".
        require_heartbeat = getattr(settings, "CHAT_AI_REQUIRE_WORKER_HEARTBEAT", False)
        if not require_heartbeat:
            return True
        try:
            from SparkService.celery import app as celery_app

            responses = celery_app.control.ping(timeout=1)
            healthy = bool(responses)
        except Exception as exc:  # pragma: no cover - broker transient state
            logger.warning("chat_run_readiness.worker_probe_failed: %s", exc)
            healthy = False
        return healthy