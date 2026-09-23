from __future__ import annotations

import hashlib
import hmac

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from subscriptions.models import RevenueCatOwnershipConflictEvent, RevenueCatSubscriptionOwnership


class OwnershipConflict(Exception):
    """The transaction is permanently owned by another SparkService account."""


class OwnershipUnverifiable(Exception):
    """The provider response does not contain enough data to bind ownership."""


def account_fingerprint(account_id: int) -> str:
    secret = str(getattr(settings, "REVENUECAT_OWNERSHIP_FINGERPRINT_SECRET", "")).encode("utf-8")
    if not secret:
        secret = str(getattr(settings, "SECRET_KEY", "")).encode("utf-8")
    return hmac.new(secret, str(account_id).encode("utf-8"), hashlib.sha256).hexdigest()


def transaction_suffix(transaction_id: str) -> str:
    value = str(transaction_id or "")
    return value[-4:] if value else ""


class RevenueCatSubscriptionOwnershipService:
    @staticmethod
    def bind_or_validate(*, user, item, trigger: str, request_id: str = ""):
        original_transaction_id = str(item.original_transaction_id or "").strip()
        if not original_transaction_id:
            raise OwnershipUnverifiable("missing_original_transaction_id")

        lookup = {
            "store": str(item.store or "unknown")[:32],
            "environment": str(item.environment or "").lower()[:16],
            "original_transaction_id": original_transaction_id,
        }
        with transaction.atomic():
            ownership = RevenueCatSubscriptionOwnership.objects.select_for_update().filter(**lookup).first()
            if ownership is None:
                try:
                    return RevenueCatSubscriptionOwnership.objects.create(
                        user=user,
                        state=RevenueCatSubscriptionOwnership.State.ACTIVE,
                        owner_account_fingerprint=account_fingerprint(user.id),
                        first_product_id=str(item.product_id or "")[:255],
                        first_bound_at=timezone.now(),
                        last_verified_at=timezone.now(),
                        **lookup,
                    )
                except IntegrityError:
                    ownership = RevenueCatSubscriptionOwnership.objects.select_for_update().get(**lookup)

            is_conflict = ownership.user_id != user.id or ownership.state != RevenueCatSubscriptionOwnership.State.ACTIVE
            if not is_conflict:
                ownership.last_verified_at = timezone.now()
                ownership.save(update_fields=["last_verified_at", "updated_at"])
                return ownership

        # Keep the audit record even though the caller will turn this into a
        # deterministic sync failure; it must not be rolled back with the lock
        # transaction above.
        if is_conflict:
            RevenueCatOwnershipConflictEvent.objects.create(
                ownership=ownership,
                attempted_user=user,
                trigger=str(trigger or "sync")[:32],
                store=lookup["store"],
                environment=lookup["environment"],
                transaction_suffix=transaction_suffix(original_transaction_id),
                request_id=str(request_id or "")[:64],
            )
            raise OwnershipConflict("subscription_sync_failed")

    @staticmethod
    def matches(*, user, snapshot) -> bool:
        transaction_id = str(snapshot.original_transaction_id or "").strip()
        if not transaction_id:
            return False
        return RevenueCatSubscriptionOwnership.objects.filter(
            user=user,
            store=snapshot.store,
            environment=snapshot.environment,
            original_transaction_id=transaction_id,
            state=RevenueCatSubscriptionOwnership.State.ACTIVE,
        ).exists()

    @staticmethod
    @transaction.atomic
    def tombstone_user(*, user):
        now = timezone.now()
        return RevenueCatSubscriptionOwnership.objects.filter(user=user).update(
            user=None,
            state=RevenueCatSubscriptionOwnership.State.TOMBSTONE,
            tombstoned_at=now,
            updated_at=now,
        )
