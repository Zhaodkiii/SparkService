from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView

from backoffice.audit import write_audit_log
from common.permissions import AdminCodePermission, AdminOnlyPermission
from common.response import error_response, success_response
from subscriptions.models import RevenueCatEntitlement, RevenueCatWebhookEvent
from subscriptions.models import RevenueCatOwnershipConflictEvent, RevenueCatSubscriptionOwnership
from subscriptions.services.revenuecat_client import RevenueCatProviderError
from subscriptions.services.subscription_sync_service import RevenueCatSubscriptionSyncService
from subscriptions.tasks import process_revenuecat_webhook_event


def _event_payload(row: RevenueCatWebhookEvent) -> dict:
    return {
        "event_id": row.event_id,
        "event_type": row.event_type,
        "environment": row.environment,
        "process_status": row.process_status,
        "attempt_count": row.attempt_count,
        "matched_user_id": row.matched_user_id,
        "error_code": row.error_code,
        "received_at": row.received_at,
        "processed_at": row.processed_at,
    }


class AdminSubscriptionUserView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, user_id: int):
        user = get_object_or_404(get_user_model(), pk=user_id)
        snapshots = list(RevenueCatEntitlement.objects.filter(user=user).values(
            "entitlement_identifier", "environment", "status", "product_id", "expires_at", "will_renew", "last_synced_at",
            "billing_status", "pending_product_id", "revoked_at", "store",
        ))
        ownerships = list(RevenueCatSubscriptionOwnership.objects.filter(user=user).values(
            "store", "environment", "state", "first_product_id", "first_bound_at", "last_verified_at", "tombstoned_at",
        ))
        conflicts = RevenueCatOwnershipConflictEvent.objects.filter(attempted_user=user).count()
        return success_response(
            {"user_id": user.id, "summary": RevenueCatSubscriptionSyncService.current_summary(user=user), "snapshots": snapshots, "ownerships": ownerships, "ownership_conflict_count": conflicts},
            msg="success",
        )


class AdminSubscriptionEventListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        rows = RevenueCatWebhookEvent.objects.all().order_by("-received_at", "-id")
        for field in ("process_status", "environment", "event_type", "event_id"):
            value = (request.query_params.get(field) or "").strip()
            if value:
                rows = rows.filter(**{field: value})
        user_id = (request.query_params.get("user_id") or "").strip()
        if user_id.isdigit():
            rows = rows.filter(matched_user_id=int(user_id))
        try:
            page = max(1, int(request.query_params.get("page", "1") or 1))
            page_size = min(100, max(1, int(request.query_params.get("page_size", "20") or 20)))
        except (TypeError, ValueError):
            return error_response("invalid_pagination", code=42022, status_code=status.HTTP_400_BAD_REQUEST)
        page_obj = Paginator(rows, page_size).get_page(page)
        return success_response(
            {"items": [_event_payload(row) for row in page_obj.object_list], "page": page_obj.number, "page_size": page_size, "total": page_obj.paginator.count},
            msg="success",
        )


class AdminSubscriptionEventReplayView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:subscription:event:replay"

    def post(self, request, event_id: str):
        row = get_object_or_404(RevenueCatWebhookEvent, event_id=event_id)
        if row.process_status in (
            RevenueCatWebhookEvent.ProcessStatus.PROCESSED,
            RevenueCatWebhookEvent.ProcessStatus.OWNERSHIP_CONFLICT,
        ):
            return error_response("event_already_processed", code=42020, status_code=status.HTTP_409_CONFLICT)
        row.process_status = RevenueCatWebhookEvent.ProcessStatus.RECEIVED
        row.next_retry_at = None
        row.error_code = ""
        row.error_message = ""
        row.save(update_fields=["process_status", "next_retry_at", "error_code", "error_message"])
        process_revenuecat_webhook_event.delay(row.event_id)
        payload = _event_payload(row)
        write_audit_log(request, action="admin.subscription.event.replay", resource_type="revenuecat_webhook_event", resource_id=row.event_id, response_payload=payload)
        return success_response(payload, msg="replay_queued", status_code=status.HTTP_202_ACCEPTED)


class AdminSubscriptionUserSyncView(APIView):
    permission_classes = [AdminCodePermission]
    required_permission_code = "button:subscription:user:sync"

    def post(self, request, user_id: int):
        user = get_object_or_404(get_user_model(), pk=user_id)
        try:
            payload = RevenueCatSubscriptionSyncService.sync_user(user=user, reason="admin_manual_sync")
        except RevenueCatProviderError as exc:
            if exc.code == "subscription_sync_failed":
                return error_response("subscription_sync_failed", code=42024, status_code=status.HTTP_409_CONFLICT)
            return error_response("subscription_sync_failed", code=42021, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        write_audit_log(request, action="admin.subscription.user.sync", resource_type="user", resource_id=str(user.id), response_payload=payload)
        return success_response(payload, msg="synced")
