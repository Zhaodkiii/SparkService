from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from chat_sync.ai_api.serializers import (
    CreateRunSerializer,
    InteractionClaimSerializer,
    InteractionHeartbeatSerializer,
    InteractionRefuseSerializer,
    InteractionResponseSerializer,
    PreferencesSerializer,
    ContextSummarySerializer,
    DeferredToolLoadSerializer,
    DeferredToolRevokeSerializer,
)
from chat_sync.ai_models import ChatThreadPreferences, ChatTurnContextSnapshot, ChatWebSocketTicket
from chat_sync.models import ChatThread
from chat_sync.ai_services.run_service import RunService
from common.response import success_response
from chat_sync.ai_services.pending_interaction_service import PendingInteractionService
from chat_sync.ai_services.deferred_tool_service import DeferredToolService
from chat_sync.ai_runtime.capabilities import build_capability_registry

logger = logging.getLogger("chat_sync.ai.api")


def _request_id(request) -> str:
    return str(request.headers.get("X-Request-ID") or "-")[:128]


class WebSocketTicketView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ttl = max(5, min(120, int(getattr(settings, "CHAT_AI_WS_TICKET_TTL_SECONDS", 30))))
        raw_ticket = secrets.token_urlsafe(32)
        now = timezone.now()
        ChatWebSocketTicket.objects.create(
            user=request.user,
            token_hash=hashlib.sha256(raw_ticket.encode("utf-8")).hexdigest(),
            websocket_path="/ws/chat/runs/",
            expires_at=now + timedelta(seconds=ttl),
        )
        ChatWebSocketTicket.objects.filter(expires_at__lt=now - timedelta(minutes=5)).delete()
        return success_response(
            {"ticket": raw_ticket, "expires_in": ttl, "websocket_path": "/ws/chat/runs/"},
            msg="created",
            status_code=201,
        )


class CapabilitiesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        registry = build_capability_registry()
        return success_response(
            {
                "capabilities": [item.to_dict() for item in registry.list()],
                "registry_version": "p6.v1",
            },
            msg="ok",
        )


class DeferredToolCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, thread_id):
        run_id = request.query_params.get("run_id")
        return success_response(
            DeferredToolService.catalog(user_id=request.user.id, thread_id=thread_id, run_id=run_id),
            msg="ok",
        )


class DeferredToolLoadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, thread_id):
        serializer = DeferredToolLoadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = DeferredToolService.load(
            user_id=request.user.id,
            thread_id=thread_id,
            run_id=serializer.validated_data["run_id"],
            names=serializer.validated_data["names"],
        )
        return success_response(result, msg="loaded", status_code=200)


class DeferredToolRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, thread_id):
        serializer = DeferredToolRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = DeferredToolService.revoke(
            user_id=request.user.id,
            thread_id=thread_id,
            names=serializer.validated_data["names"],
            reason=serializer.validated_data.get("reason", "user_revoked"),
        )
        return success_response({"revoked": result}, msg="revoked", status_code=200)


class CreateRunView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, thread_id):
        serializer = CreateRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = RunService.create_run(
            user=request.user,
            thread_id=thread_id,
            payload=serializer.validated_data,
            idempotency_key=request.headers.get("Idempotency-Key"),
            request_id=_request_id(request),
        )
        payload = {
            "run": RunService.serialize_run(result.run),
            "subscription": {
                "websocket_path": "/ws/chat/runs/",
                "resume_after_sequence": 0,
            },
        }
        return success_response(payload, msg="replayed" if result.replayed else "accepted", status_code=200 if result.replayed else 202)


class ThreadPreferencesView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, thread_id, lock=False):
        thread = ChatThread.objects.filter(id=thread_id, user=request.user, is_deleted=False).first()
        if thread is None:
            from common.exceptions import APIError
            raise APIError("chat_thread_not_found", code=40491, status_code=404)
        prefs, _ = ChatThreadPreferences.objects.get_or_create(thread=thread)
        return prefs

    def get(self, request, thread_id):
        prefs = self.get_object(request, thread_id)
        data = PreferencesSerializer(prefs).data
        return success_response(data, msg="ok")

    def patch(self, request, thread_id):
        from django.db import transaction
        from common.exceptions import APIError

        serializer = PreferencesSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            prefs = self.get_object(request, thread_id)
            expected = request.headers.get("If-Match") or request.data.get("revision")
            try:
                expected = int(str(expected).strip('"'))
            except (TypeError, ValueError):
                raise APIError("chat_preferences_revision_required", code=42891, status_code=428)
            if expected != prefs.revision:
                raise APIError("chat_preferences_revision_conflict", code=40993, status_code=409, details={"revision": prefs.revision})
            for key, value in serializer.validated_data.items():
                if key != "revision":
                    setattr(prefs, key, list(dict.fromkeys(value)) if key in {"enabled_tools", "knowledge_bases"} else value)
            prefs.revision += 1
            prefs.save()
        response = success_response(PreferencesSerializer(prefs).data, msg="updated")
        response["ETag"] = f'"{prefs.revision}"'
        return response


class RunDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        run = RunService.get_run(user_id=request.user.id, run_id=run_id)
        return success_response({"run": RunService.serialize_run(run)}, msg="ok")


class RunContextSummaryView(APIView):
    """Return an allow-listed, non-sensitive projection of a Run context snapshot."""

    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        run = RunService.get_run(user_id=request.user.id, run_id=run_id)
        snapshot = ChatTurnContextSnapshot.objects.filter(run=run).first()
        if snapshot is None:
            data = {
                "run_id": run.id,
                "build_status": "pending",
                "preferences_revision": (run.request_snapshot or {}).get("preferences_revision"),
                "language": str(((run.request_snapshot or {}).get("preferences") or {}).get("language") or "zh-CN"),
                "history": {"selected_count": 0, "trimmed": False, "summary_used": False},
                "budget_level": "normal",
                "sources": [],
            }
            return success_response(ContextSummarySerializer(data).data, msg="ok")

        sources = []
        for item in snapshot.sources or []:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            sources.append(
                {
                    "source_id": str(item.get("source_id") or "")[:255],
                    "type": str(item.get("type") or "unknown")[:64],
                    "title": str(item.get("title") or "")[:255],
                    "availability": "metadata_only" if metadata.get("content_status") == "unavailable" else "available",
                }
            )
        budget = snapshot.token_budget if isinstance(snapshot.token_budget, dict) else {}
        input_budget = int(budget.get("input_budget") or 0)
        used_tokens = int(budget.get("used_tokens") or 0)
        budget_level = "normal"
        if input_budget and used_tokens >= input_budget:
            budget_level = "exceeded"
        elif input_budget and used_tokens >= int(input_budget * 0.8):
            budget_level = "near_limit"
        data = {
            "run_id": run.id,
            "build_status": snapshot.build_status,
            "preferences_revision": snapshot.preferences_revision,
            "language": snapshot.language or "zh-CN",
            "history": {
                "selected_count": len(snapshot.selected_message_ids or []),
                "trimmed": bool(snapshot.trim_trace),
                "summary_used": bool(snapshot.history_summary),
            },
            "budget_level": budget_level,
            "sources": sources,
        }
        return success_response(ContextSummarySerializer(data).data, msg="ok")


class RunEventsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        try:
            after_sequence = int(request.query_params.get("after_sequence", "0"))
            limit = int(request.query_params.get("limit", "200"))
        except (TypeError, ValueError):
            from common.exceptions import APIError

            raise APIError("chat_run_request_invalid", code=40091, status_code=400, details={"field": "cursor"})
        events = RunService.list_events(
            user_id=request.user.id,
            run_id=run_id,
            after_sequence=after_sequence,
            limit=limit,
        )
        next_sequence = events[-1].sequence if events else after_sequence
        run = RunService.get_run(user_id=request.user.id, run_id=run_id)
        return success_response(
            {
                "events": [RunService.serialize_event(event) for event in events],
                "next_after_sequence": next_sequence,
                "has_more": next_sequence < run.last_sequence,
            },
            msg="ok",
        )


class RunCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, run_id):
        run = RunService.request_cancel(user_id=request.user.id, run_id=run_id, request_id=_request_id(request))
        return success_response({"run": RunService.serialize_run(run)}, msg="cancel_requested")


class RunRegenerateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, run_id):
        result = RunService.regenerate(
            user=request.user,
            run_id=run_id,
            idempotency_key=request.headers.get("Idempotency-Key"),
            request_id=_request_id(request),
        )
        return success_response(
            {"run": RunService.serialize_run(result.run)},
            msg="replayed" if result.replayed else "accepted",
            status_code=200 if result.replayed else 202,
        )


class ActiveRunView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, thread_id):
        from chat_sync.ai_models import ChatThreadRunLock
        from chat_sync.models import ChatThread

        thread = ChatThread.objects.filter(id=thread_id, user=request.user, is_deleted=False).first()
        if thread is None:
            from common.exceptions import APIError

            raise APIError("chat_thread_not_found", code=40491, status_code=404)
        lock = ChatThreadRunLock.objects.select_related("active_run").filter(thread=thread).first()
        run = lock.active_run if lock and lock.active_run and not lock.active_run.is_terminal else None
        return success_response({"run": RunService.serialize_run(run) if run else None}, msg="ok")


class PendingInteractionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        run = RunService.get_run(user_id=request.user.id, run_id=run_id)
        interactions = PendingInteractionService.list_pending(user_id=request.user.id, run_id=run.id)
        return success_response({"interactions": [PendingInteractionService.serialize(item) for item in interactions]}, msg="ok")


class InteractionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, interaction_id):
        interaction = PendingInteractionService.get_for_read(user_id=request.user.id, public_id=interaction_id)
        return success_response({"interaction": PendingInteractionService.serialize(interaction)}, msg="ok")


class InteractionClaimView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, interaction_id):
        serializer = InteractionClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        interaction, token = PendingInteractionService.claim(user_id=request.user.id, public_id=interaction_id, **serializer.validated_data)
        return success_response({"interaction": PendingInteractionService.serialize(interaction), "claim_token": token}, msg="claimed", status_code=200)


class InteractionHeartbeatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, interaction_id):
        data = dict(request.data or {})
        data.setdefault("claim_token", request.headers.get("X-Interaction-Claim", ""))
        serializer = InteractionHeartbeatSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        interaction = PendingInteractionService.heartbeat(user_id=request.user.id, public_id=interaction_id, **serializer.validated_data)
        return success_response({"interaction": PendingInteractionService.serialize(interaction)}, msg="heartbeat")


class InteractionResponseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, interaction_id):
        serializer = InteractionResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = PendingInteractionService.resolve(
            user_id=request.user.id,
            public_id=interaction_id,
            response=serializer.validated_data["response"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            device_id=serializer.validated_data.get("device_id", ""),
            claim_token=serializer.validated_data.get("claim_token") or request.headers.get("X-Interaction-Claim", ""),
        )
        return success_response({"interaction": PendingInteractionService.serialize(result.interaction), "run": RunService.serialize_run(result.run), "accepted": not result.replayed, "replayed": result.replayed}, msg="replayed" if result.replayed else "accepted", status_code=200 if result.replayed else 202)


class InteractionRefuseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, interaction_id):
        serializer = InteractionRefuseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = PendingInteractionService.resolve(
            user_id=request.user.id,
            public_id=interaction_id,
            response={"resolution": "refused", "reason": serializer.validated_data.get("reason", "user_refused")},
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            device_id=serializer.validated_data.get("device_id", ""),
            claim_token=serializer.validated_data.get("claim_token") or request.headers.get("X-Interaction-Claim", ""),
        )
        return success_response({"interaction": PendingInteractionService.serialize(result.interaction), "run": RunService.serialize_run(result.run), "replayed": result.replayed}, msg="replayed" if result.replayed else "accepted", status_code=200 if result.replayed else 202)
