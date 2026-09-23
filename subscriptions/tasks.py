from datetime import datetime, timedelta, timezone as datetime_timezone
import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from subscriptions.models import RevenueCatEntitlement, RevenueCatWebhookEvent
from subscriptions.services.revenuecat_client import RevenueCatProviderError
from subscriptions.services.subscription_sync_service import RevenueCatSubscriptionSyncService
from subscriptions.services.webhook_inbox_service import RevenueCatWebhookInboxService

logger = logging.getLogger(__name__)


def _event_datetime(value):
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=datetime_timezone.utc) if value else None
    except (TypeError, ValueError, OverflowError):
        return None


def _apply_event_metadata(*, row: RevenueCatWebhookEvent, users: list):
    event = row.payload if isinstance(row.payload, dict) else {}
    event_type = str(row.event_type or "").upper()
    reason = str(event.get("cancel_reason") or event.get("expiration_reason") or "").upper()
    environment = str(row.environment or "").lower()
    entitlement_identifier = str(getattr(settings, "REVENUECAT_ENTITLEMENT_IDENTIFIER", "健康Pro"))
    event_ms = int(row.event_timestamp_ms or 0)
    for user in users:
        snapshot = RevenueCatEntitlement.objects.filter(
            user=user,
            entitlement_identifier=entitlement_identifier,
            environment=environment,
        ).first()
        if snapshot is None or event_ms < snapshot.last_event_timestamp_ms:
            continue
        update_fields = ["last_event_type", "last_event_timestamp_ms"]
        snapshot.last_event_type = event_type[:64]
        snapshot.last_event_timestamp_ms = event_ms
        if event_type == "BILLING_ISSUE":
            snapshot.billing_status = "grace_period" if _event_datetime(event.get("grace_period_expiration_at_ms")) else "billing_issue"
            snapshot.billing_issue_detected_at = _event_datetime(event.get("event_timestamp_ms") or event_ms)
            snapshot.grace_period_expires_at = _event_datetime(event.get("grace_period_expiration_at_ms"))
            update_fields += ["billing_status", "billing_issue_detected_at", "grace_period_expires_at"]
        elif event_type == "CANCELLATION":
            if reason == "BILLING_ERROR":
                snapshot.billing_status = "billing_issue"
                snapshot.billing_issue_detected_at = _event_datetime(event.get("event_timestamp_ms") or event_ms)
                update_fields += ["billing_status", "billing_issue_detected_at"]
            else:
                snapshot.will_renew = False
                snapshot.unsubscribe_detected_at = _event_datetime(event.get("event_timestamp_ms") or event_ms)
                update_fields += ["will_renew", "unsubscribe_detected_at"]
        elif event_type == "PRODUCT_CHANGE":
            snapshot.pending_product_id = str(event.get("new_product_id") or "")[:255]
            update_fields.append("pending_product_id")
        elif event_type == "EXPIRATION":
            snapshot.status = RevenueCatEntitlement.Status.REVOKED if reason in {"CUSTOMER_SUPPORT", "DEVELOPER_INITIATED"} else RevenueCatEntitlement.Status.EXPIRED
            snapshot.revoked_at = timezone.now() if snapshot.status == RevenueCatEntitlement.Status.REVOKED else None
            update_fields += ["status", "revoked_at"]
        elif event_type in {"RENEWAL", "UNCANCELLATION", "REFUND_REVERSED", "SUBSCRIPTION_EXTENDED"}:
            snapshot.billing_status = "normal"
            snapshot.billing_issue_detected_at = None
            snapshot.grace_period_expires_at = None
            update_fields += ["billing_status", "billing_issue_detected_at", "grace_period_expires_at"]
        snapshot.save(update_fields=update_fields + ["updated_at"])


@shared_task(bind=True, max_retries=8, default_retry_delay=60)
def process_revenuecat_webhook_event(self, event_id: str):
    with transaction.atomic():
        row = RevenueCatWebhookEvent.objects.select_for_update().filter(event_id=event_id).first()
        if row is None or row.process_status == RevenueCatWebhookEvent.ProcessStatus.PROCESSED:
            return {"status": "skipped"}
        row.process_status = RevenueCatWebhookEvent.ProcessStatus.PROCESSING
        row.attempt_count += 1
        row.locked_at = timezone.now()
        row.save(update_fields=["process_status", "attempt_count", "locked_at"])
    try:
        users = RevenueCatWebhookInboxService.match_users(row=row)
        if not users:
            row.process_status = RevenueCatWebhookEvent.ProcessStatus.UNMATCHED
            row.next_retry_at = timezone.now() + timedelta(minutes=15)
            row.error_code = "user_unmatched"
            row.save(update_fields=["process_status", "next_retry_at", "error_code"])
            return {"status": "unmatched"}
        # TRANSFER may name both identities in aliases. Sync every known user so neither
        # the source nor the destination keeps a stale snapshot.
        for user in users:
            RevenueCatSubscriptionSyncService.sync_user(user=user, reason=f"webhook:{row.event_type}", request_id=row.event_id)
        _apply_event_metadata(row=row, users=users)
        row.process_status = RevenueCatWebhookEvent.ProcessStatus.PROCESSED
        row.processed_at = timezone.now()
        row.error_code = ""
        row.error_message = ""
        row.next_retry_at = None
        row.save(update_fields=["process_status", "processed_at", "error_code", "error_message", "next_retry_at"])
        return {"status": "processed", "user_ids": [user.id for user in users]}
    except RevenueCatProviderError as exc:
        if exc.code == "subscription_sync_failed":
            row.process_status = RevenueCatWebhookEvent.ProcessStatus.OWNERSHIP_CONFLICT
        else:
            row.process_status = RevenueCatWebhookEvent.ProcessStatus.RETRYABLE if exc.retryable else RevenueCatWebhookEvent.ProcessStatus.FAILED
        row.error_code = exc.code
        row.error_message = "provider synchronization failed"
        row.next_retry_at = timezone.now() + timedelta(seconds=min(21600, 60 * (2 ** max(0, row.attempt_count - 1))))
        row.save(update_fields=["process_status", "error_code", "error_message", "next_retry_at"])
        if exc.retryable and row.attempt_count <= int(getattr(settings, "REVENUECAT_WEBHOOK_MAX_ATTEMPTS", 8)):
            raise self.retry(exc=exc, countdown=max(60, int((row.next_retry_at - timezone.now()).total_seconds())))
        return {"status": "failed", "reason": exc.code}
    except Exception:
        logger.exception("revenuecat.webhook.process_failed event_id=%s", event_id)
        row.process_status = RevenueCatWebhookEvent.ProcessStatus.FAILED
        row.error_code = "processing_failed"
        row.error_message = "unexpected processing failure"
        row.save(update_fields=["process_status", "error_code", "error_message"])
        raise


@shared_task
def reconcile_revenuecat_subscriptions_task(limit: int = 200):
    cutoff = timezone.now() - timedelta(hours=24)
    user_ids = list(
        RevenueCatEntitlement.objects.filter(
            environment__in=(
                RevenueCatEntitlement.Environment.PRODUCTION,
                RevenueCatEntitlement.Environment.SANDBOX,
            )
        )
        .filter(Q(status=RevenueCatEntitlement.Status.ACTIVE) | Q(last_synced_at__lt=cutoff))
        .order_by("last_synced_at")
        .values_list("user_id", flat=True)
        .distinct()[:limit]
    )
    for user_id in user_ids:
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.filter(id=user_id).first()
        if user:
            try:
                RevenueCatSubscriptionSyncService.sync_user(user=user, reason="scheduled_reconciliation")
            except Exception:
                logger.exception("revenuecat.reconcile_failed user_id=%s", user_id)
    return {"candidate_count": len(user_ids)}


@shared_task
def retry_pending_revenuecat_webhooks_task(limit: int = 100):
    now = timezone.now()
    rows = list(
        RevenueCatWebhookEvent.objects.filter(
            process_status__in=[
                RevenueCatWebhookEvent.ProcessStatus.UNMATCHED,
                RevenueCatWebhookEvent.ProcessStatus.RETRYABLE,
            ],
            next_retry_at__lte=now,
        ).order_by("next_retry_at", "id")[:limit]
    )
    for row in rows:
        process_revenuecat_webhook_event.delay(row.event_id)
    return {"queued_count": len(rows)}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_revenuecat_user_task(self, user_id: int, reason: str = "retry"):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(id=user_id, is_active=True).first()
    if user is None:
        return {"status": "user_not_found"}
    try:
        result = RevenueCatSubscriptionSyncService.sync_user(user=user, reason=reason)
        return {"status": "synced", "is_pro": result["is_pro"]}
    except RevenueCatProviderError as exc:
        if exc.retryable:
            raise self.retry(exc=exc)
        return {"status": "failed", "reason": exc.code}
