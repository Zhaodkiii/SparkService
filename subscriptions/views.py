import json
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from django.utils import timezone

from common.response import error_response, success_response
from subscriptions.models import RevenueCatSyncRequest, RevenueCatWebhookEvent
from subscriptions.services.identity_service import RevenueCatIdentityConflict
from subscriptions.services.revenuecat_client import RevenueCatProviderError
from subscriptions.services.subscription_sync_service import RevenueCatSubscriptionSyncService
from subscriptions.services.webhook_inbox_service import RevenueCatWebhookInboxService
from subscriptions.tasks import process_revenuecat_webhook_event, sync_revenuecat_user_task


logger = logging.getLogger(__name__)


class SubscriptionMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return success_response(RevenueCatSubscriptionSyncService.current_summary(user=request.user), msg="success")


class RevenueCatSubscriptionSyncView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        idempotency_key = (request.headers.get("Idempotency-Key") or "").strip()
        if len(idempotency_key) > 128:
            return error_response("invalid_idempotency_key", code=42004, status_code=status.HTTP_400_BAD_REQUEST)
        sync_request = None
        if idempotency_key:
            sync_request, created = RevenueCatSyncRequest.objects.get_or_create(
                user=request.user,
                idempotency_key=idempotency_key,
            )
            if not created and sync_request.response_payload is not None:
                if sync_request.response_status >= 400:
                    return error_response(
                        "subscription_sync_failed",
                        code=42024,
                        status_code=sync_request.response_status,
                    )
                return success_response(
                    sync_request.response_payload,
                    msg="synced",
                    status_code=sync_request.response_status,
                )
            if not created and sync_request.status == "processing":
                # A process crash can leave the row in processing forever. Only
                # treat a recent row as in-flight; an old row must be retried.
                stale_after = timezone.now() - timedelta(minutes=2)
                if sync_request.updated_at >= stale_after:
                    summary = RevenueCatSubscriptionSyncService.current_summary(user=request.user, sync_state="pending_retry")
                    return success_response(summary, msg="sync_in_progress", status_code=status.HTTP_202_ACCEPTED)
                sync_request.status = "processing"
                sync_request.response_payload = None
                sync_request.response_status = status.HTTP_200_OK
                sync_request.save(update_fields=["status", "response_payload", "response_status", "updated_at"])
        try:
            summary = RevenueCatSubscriptionSyncService.sync_user(
                user=request.user,
                reason="client_sync",
                request_id=str(getattr(request, "request_id", "") or request.headers.get("X-Request-ID", "")),
            )
            if sync_request is not None:
                sync_request.status = "completed"
                sync_request.response_payload = json.loads(json.dumps(summary, cls=DjangoJSONEncoder))
                sync_request.response_status = status.HTTP_200_OK
                sync_request.save(update_fields=["status", "response_payload", "response_status", "updated_at"])
            return success_response(summary, msg="synced", status_code=status.HTTP_200_OK)
        except RevenueCatIdentityConflict:
            return error_response("identity_conflict", code=42003, status_code=status.HTTP_409_CONFLICT)
        except RevenueCatProviderError as exc:
            if exc.code == "subscription_sync_failed":
                if sync_request is not None:
                    sync_request.status = "failed"
                    sync_request.response_payload = {"sync_state": "failed"}
                    sync_request.response_status = status.HTTP_409_CONFLICT
                    sync_request.save(update_fields=["status", "response_payload", "response_status", "updated_at"])
                return error_response("subscription_sync_failed", code=42024, status_code=status.HTTP_409_CONFLICT)
            if exc.retryable:
                # The next lifecycle/manual sync retries; never fabricate a client entitlement.
                if sync_request is not None:
                    sync_request.status = "retryable"
                    sync_request.response_payload = None
                    sync_request.response_status = status.HTTP_503_SERVICE_UNAVAILABLE
                    sync_request.save(update_fields=["status", "response_payload", "response_status", "updated_at"])
                transaction.on_commit(lambda: sync_revenuecat_user_task.delay(request.user.id, "client_sync_retry"))
                summary = RevenueCatSubscriptionSyncService.current_summary(user=request.user, sync_state="pending_retry")
                return success_response(summary, msg="sync_pending_retry", status_code=status.HTTP_202_ACCEPTED)
            return error_response("subscription_sync_unavailable", code=42002, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception:
            # Unexpected provider/parser errors must not leave an idempotency row
            # permanently stuck in processing and must not expose internals.
            logger.exception("revenuecat.subscription_sync_unexpected user_id=%s", request.user.id)
            if sync_request is not None:
                sync_request.status = "failed"
                sync_request.response_payload = {"sync_state": "failed"}
                sync_request.response_status = status.HTTP_503_SERVICE_UNAVAILABLE
                sync_request.save(update_fields=["status", "response_payload", "response_status", "updated_at"])
            return error_response("subscription_sync_unavailable", code=42002, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


class RevenueCatWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        expected = str(getattr(settings, "REVENUECAT_WEBHOOK_AUTHORIZATION", "")).strip()
        received = request.headers.get("Authorization") or ""
        if not expected or not secrets.compare_digest(received, expected):
            return error_response("unauthorized", code=42010, status_code=status.HTTP_401_UNAUTHORIZED)
        if not isinstance(request.data, dict):
            return error_response("invalid_payload", code=42011, status_code=status.HTTP_400_BAD_REQUEST)
        event = request.data.get("event", request.data)
        if not isinstance(event, dict):
            return error_response("invalid_payload", code=42011, status_code=status.HTTP_400_BAD_REQUEST)
        environment = str(event.get("environment") or "").lower()
        allowed_environments = set(getattr(settings, "REVENUECAT_WEBHOOK_ALLOWED_ENVIRONMENTS", ("production", "sandbox")))
        if environment and environment not in allowed_environments:
            return error_response("invalid_environment", code=42012, status_code=status.HTTP_400_BAD_REQUEST)
        app_id = str(event.get("app_id") or "").strip()
        allowed_app_ids = set(getattr(settings, "REVENUECAT_WEBHOOK_ALLOWED_APP_IDS", ()))
        if allowed_app_ids and app_id not in allowed_app_ids:
            return error_response("invalid_app", code=42013, status_code=status.HTTP_400_BAD_REQUEST)
        try:
            row, created = RevenueCatWebhookInboxService.enqueue(event=event)
        except (TypeError, ValueError):
            return error_response("invalid_payload", code=42011, status_code=status.HTTP_400_BAD_REQUEST)
        if created:
            transaction.on_commit(lambda: process_revenuecat_webhook_event.delay(row.event_id))
        # Duplicate deliveries are acknowledged to preserve RevenueCat's at-least-once contract.
        return success_response({"event_id": row.event_id, "accepted": created}, msg="accepted", status_code=status.HTTP_200_OK)
