from django.conf import settings
from django.utils import timezone

from ai_config.models import TrialApplication
from ai_config.services import TrialService
from subscriptions.models import RevenueCatEntitlement
from subscriptions.services.ownership_service import RevenueCatSubscriptionOwnershipService


class ProEntitlementResolver:
    @staticmethod
    def is_pro_user(*, user) -> bool:
        return bool(ProEntitlementResolver.resolve(user=user)["is_pro"])

    @staticmethod
    def _allowed_environments() -> tuple[str, ...]:
        configured = getattr(settings, "REVENUECAT_AUTHORIZATION_ENVIRONMENTS", None)
        if configured is None:
            configured = getattr(settings, "REVENUECAT_SYNC_ENVIRONMENTS", (RevenueCatEntitlement.Environment.PRODUCTION,))
        return tuple(str(item).lower() for item in configured if str(item).strip())

    @staticmethod
    def _latest_snapshot(*, user):
        return (
            RevenueCatEntitlement.objects.filter(
                user=user,
                entitlement_identifier=str(getattr(settings, "REVENUECAT_ENTITLEMENT_IDENTIFIER", "健康Pro")),
                environment__in=ProEntitlementResolver._allowed_environments(),
            )
            .order_by("-last_synced_at", "-id")
            .first()
        )

    @staticmethod
    def _serialize_revenuecat(snapshot, *, active: bool, now):
        identifier = str(getattr(settings, "REVENUECAT_ENTITLEMENT_IDENTIFIER", "健康Pro"))
        if snapshot is None:
            return {
                "type": "revenuecat", "active": False, "status": "unknown", "billing_status": "unknown",
                "environment": None, "entitlement": identifier, "product_id": "", "pending_product_id": "",
                "started_at": None, "expires_at": None, "will_renew": False, "period_type": "", "store": "",
                "last_synced_at": None,
            }

        status = snapshot.status
        if status == RevenueCatEntitlement.Status.ACTIVE and snapshot.expires_at and snapshot.expires_at <= now:
            status = RevenueCatEntitlement.Status.EXPIRED
            active = False
        return {
            "type": "revenuecat", "active": bool(active), "status": status,
            "billing_status": snapshot.billing_status or "unknown", "environment": snapshot.environment,
            "entitlement": snapshot.entitlement_identifier, "product_id": snapshot.product_id,
            "pending_product_id": snapshot.pending_product_id, "started_at": snapshot.started_at,
            "expires_at": snapshot.expires_at, "will_renew": bool(snapshot.will_renew),
            "period_type": snapshot.period_type, "store": snapshot.store, "last_synced_at": snapshot.last_synced_at,
        }

    @staticmethod
    def resolve(*, user) -> dict:
        now = timezone.now()
        snapshot = ProEntitlementResolver._latest_snapshot(user=user)
        owned = bool(snapshot and RevenueCatSubscriptionOwnershipService.matches(user=user, snapshot=snapshot))
        revenuecat_active = bool(
            snapshot and owned and snapshot.status == RevenueCatEntitlement.Status.ACTIVE
            and snapshot.revoked_at is None and snapshot.expires_at is not None and snapshot.expires_at > now
        )

        trial = TrialService.build_pro_summary(user=user)
        trial_active = bool(trial["is_pro"] and trial.get("grant_source") != TrialApplication.GrantSource.MANUAL)
        manual_active = bool(trial["is_pro"] and trial.get("grant_source") == TrialApplication.GrantSource.MANUAL)
        sources = [
            ProEntitlementResolver._serialize_revenuecat(snapshot, active=revenuecat_active, now=now),
            {"type": "trial", "active": trial_active, "status": trial.get("status"), "expires_at": trial.get("expires_at"), "started_at": trial.get("started_at")},
            {"type": "manual", "active": manual_active, "status": trial.get("status"), "expires_at": trial.get("expires_at") if manual_active else None, "started_at": trial.get("started_at") if manual_active else None},
        ]
        effective_source = "revenuecat" if revenuecat_active else "manual" if manual_active else "trial" if trial_active else "none"
        return {
            "is_pro": bool(revenuecat_active or trial_active or manual_active),
            "effective_source": effective_source,
            "sources": sources,
            "revenuecat_active": revenuecat_active,
            "trial_active": trial_active,
            "manual_active": manual_active,
        }
