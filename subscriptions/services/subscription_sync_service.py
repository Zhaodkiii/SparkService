from __future__ import annotations

from datetime import datetime, timezone as datetime_timezone

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from subscriptions.models import RevenueCatEntitlement
from subscriptions.services.identity_service import RevenueCatIdentityService
from subscriptions.services.ownership_service import (
    OwnershipConflict,
    OwnershipUnverifiable,
    RevenueCatSubscriptionOwnershipService,
)
from subscriptions.services.pro_entitlement_resolver import ProEntitlementResolver
from subscriptions.services.revenuecat_client import RevenueCatClient, RevenueCatProviderError


def _from_ms(value: int | None):
    return datetime.fromtimestamp(value / 1000, tz=datetime_timezone.utc) if value else None


class RevenueCatSubscriptionSyncService:
    @staticmethod
    def _sync_environments() -> tuple[str, ...]:
        configured = getattr(settings, "REVENUECAT_SYNC_ENVIRONMENTS", (RevenueCatEntitlement.Environment.PRODUCTION,))
        return tuple(str(item).lower() for item in configured if str(item).strip())

    @staticmethod
    def _entitlement_id() -> str:
        value = str(getattr(settings, "REVENUECAT_ENTITLEMENT_ID", "")).strip()
        if not value:
            raise RevenueCatProviderError("revenuecat_entitlement_not_configured", retryable=False)
        return value

    @staticmethod
    def _write_snapshot(*, user, environment: str, entitlement_identifier: str, active, reason: str, now):
        with transaction.atomic():
            snapshot, _ = RevenueCatEntitlement.objects.select_for_update().get_or_create(
                user=user,
                entitlement_identifier=entitlement_identifier,
                environment=environment,
                defaults={"status": RevenueCatEntitlement.Status.UNKNOWN},
            )
            if active is not None:
                snapshot.status = RevenueCatEntitlement.Status.ACTIVE
                snapshot.product_id = active.product_id
                snapshot.store = active.store
                snapshot.period_type = active.period_type
                snapshot.started_at = _from_ms(active.started_at_ms)
                snapshot.expires_at = _from_ms(active.expires_at_ms)
                snapshot.will_renew = active.will_renew
                snapshot.original_transaction_id = active.original_transaction_id
                snapshot.billing_status = "normal"
                snapshot.revoked_at = None
                snapshot.last_event_type = str(reason or "sync")[:64]
                snapshot.last_event_timestamp_ms = int(now.timestamp() * 1000)
                snapshot.provider_updated_at = now
            elif snapshot.status != RevenueCatEntitlement.Status.REVOKED:
                snapshot.status = RevenueCatEntitlement.Status.EXPIRED
                snapshot.will_renew = False
                snapshot.billing_status = "unknown"
                snapshot.last_event_type = str(reason or "sync")[:64]
                snapshot.last_event_timestamp_ms = int(now.timestamp() * 1000)
                snapshot.provider_updated_at = now
            snapshot.save()
            return snapshot

    @staticmethod
    def sync_user(*, user, reason: str, request_id: str = "") -> dict:
        identity = RevenueCatIdentityService.ensure_identity(user=user)
        attempt_at = timezone.now()
        identity.last_sync_attempt_at = attempt_at
        identity.save(update_fields=["last_sync_attempt_at", "updated_at"])
        entitlement_identifier = str(getattr(settings, "REVENUECAT_ENTITLEMENT_IDENTIFIER", "健康Pro"))
        entitlement_id = RevenueCatSubscriptionSyncService._entitlement_id()
        client = RevenueCatClient()

        # Provider requests intentionally happen outside a database transaction.
        provider_results: dict[str, object | None] = {}
        for environment in RevenueCatSubscriptionSyncService._sync_environments():
            items = client.get_active_entitlements(customer_id=identity.app_user_id, environment=environment)
            active = next((item for item in items if item.entitlement_id == entitlement_id), None)
            if active is not None and not active.original_transaction_id:
                raise RevenueCatProviderError("revenuecat_missing_original_transaction_id", retryable=False)
            provider_results[environment] = active

        try:
            for environment, active in provider_results.items():
                if active is not None:
                    RevenueCatSubscriptionOwnershipService.bind_or_validate(
                        user=user,
                        item=active,
                        trigger=reason,
                        request_id=request_id,
                    )
                RevenueCatSubscriptionSyncService._write_snapshot(
                    user=user,
                    environment=environment,
                    entitlement_identifier=entitlement_identifier,
                    active=active,
                    reason=reason,
                    now=attempt_at,
                )
        except OwnershipConflict as exc:
            identity.last_sync_error_code = "ownership_conflict"
            identity.save(update_fields=["last_sync_error_code", "updated_at"])
            raise RevenueCatProviderError("subscription_sync_failed", retryable=False) from exc
        except OwnershipUnverifiable as exc:
            identity.last_sync_error_code = "ownership_unverifiable"
            identity.save(update_fields=["last_sync_error_code", "updated_at"])
            raise RevenueCatProviderError("revenuecat_missing_original_transaction_id", retryable=False) from exc

        identity.last_successful_sync_at = attempt_at
        identity.last_sync_error_code = ""
        identity.save(update_fields=["last_successful_sync_at", "last_sync_error_code", "updated_at"])
        result = ProEntitlementResolver.resolve(user=user)
        result.update({"sync_state": "synced", "last_synced_at": attempt_at})
        return result

    @staticmethod
    def current_summary(*, user, sync_state: str = "synced") -> dict:
        result = ProEntitlementResolver.resolve(user=user)
        identity = getattr(user, "revenuecat_identity", None)
        result.update({"sync_state": sync_state, "last_synced_at": identity.last_successful_sync_at if identity else None})
        return result
