from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from common.exceptions import APIError
from chat_sync.ai_services.run_readiness_service import ChatRunReadinessService


class _Route:
    config_version = "2026-08-25T00:00:00+00:00"


class RunReadinessServiceTests(TestCase):
    @override_settings(CHAT_AI_SERVER_RUNS_ENABLED=False)
    def test_flag_off_is_unavailable(self):
        r = ChatRunReadinessService.evaluate()
        self.assertFalse(r.available)
        self.assertEqual(r.code, "chat_server_runs_disabled")
        self.assertFalse(r.retryable)

    @override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="disabled")
    def test_executor_disabled_is_unavailable(self):
        r = ChatRunReadinessService.evaluate()
        self.assertFalse(r.available)
        self.assertEqual(r.code, "chat_run_executor_unavailable")

    @override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="provider")
    @patch("chat_sync.ai_runtime.providers.factory.resolve_chat_route", return_value=_Route())
    def test_available_when_binding_and_worker_ok(self, _resolve):
        r = ChatRunReadinessService.evaluate()
        self.assertTrue(r.available)
        self.assertEqual(r.code, "available")
        self.assertTrue(r.worker_healthy)
        self.assertEqual(r.config_version, _Route.config_version)

    @override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="provider")
    @patch("chat_sync.ai_runtime.providers.factory.resolve_chat_route", side_effect=Exception("no binding"))
    def test_model_binding_missing(self, _resolve):
        r = ChatRunReadinessService.evaluate()
        self.assertFalse(r.available)
        self.assertEqual(r.code, "chat_run_model_binding_missing")

    @override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="provider")
    @patch("chat_sync.ai_runtime.providers.factory.resolve_chat_route", return_value=_Route())
    @patch("chat_sync.ai_services.run_readiness_service.ChatRunReadinessService.cached_worker_health", return_value=False)
    def test_worker_unavailable_is_retryable(self, _health, _resolve):
        r = ChatRunReadinessService.evaluate()
        self.assertFalse(r.available)
        self.assertEqual(r.code, "chat_run_worker_unavailable")
        self.assertTrue(r.retryable)

    @override_settings(CHAT_AI_SERVER_RUNS_ENABLED=False)
    def test_require_available_preserves_50392(self):
        with self.assertRaises(APIError) as ctx:
            ChatRunReadinessService.require_available()
        self.assertEqual(ctx.exception.code, 50392)
        self.assertEqual(ctx.exception.status_code, 503)


class RunReadinessApiTests(TestCase):
    @override_settings(CHAT_AI_SERVER_RUNS_ENABLED=True, CHAT_AI_RUN_EXECUTOR="provider")
    @patch("chat_sync.ai_runtime.providers.factory.resolve_chat_route", return_value=_Route())
    def test_readiness_endpoint_is_available_when_ready(self, _resolve):
        user = get_user_model().objects.create_user(username="readiness-user")
        client = APIClient()
        client.force_authenticate(user)
        response = client.get("/api/v1/ai/chat/readiness/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["code"], 0)
        self.assertTrue(response.data["data"]["available"])
        self.assertEqual(response.data["data"]["code"], "available")

    def test_readiness_endpoint_requires_auth(self):
        client = APIClient()
        response = client.get("/api/v1/ai/chat/readiness/")
        self.assertIn(response.status_code, (401, 403))