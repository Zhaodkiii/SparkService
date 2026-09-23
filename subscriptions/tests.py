from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from ai_config.models import TrialApplication
from subscriptions.models import (
    RevenueCatEntitlement,
    RevenueCatOwnershipConflictEvent,
    RevenueCatSubscriptionOwnership,
    RevenueCatWebhookEvent,
)
from subscriptions.services.pro_entitlement_resolver import ProEntitlementResolver
from subscriptions.services.revenuecat_client import ActiveEntitlement, RevenueCatProviderError
from subscriptions.services.revenuecat_client import RevenueCatClient
from subscriptions.services.subscription_sync_service import RevenueCatSubscriptionSyncService


@override_settings(
    REVENUECAT_ENTITLEMENT_ID="entl_health_pro",
    REVENUECAT_SYNC_ENVIRONMENTS=("production",),
    REVENUECAT_AUTHORIZATION_ENVIRONMENTS=("production",),
    REVENUECAT_WEBHOOK_ALLOWED_APP_IDS=(),
)
class RevenueCatSubscriptionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="subscription-test", email="subscription@example.com")

    @patch("subscriptions.services.subscription_sync_service.RevenueCatClient.get_active_entitlements")
    def test_sync_persists_production_entitlement_and_resolver_grants_pro(self, mock_active):
        mock_active.return_value = [
            ActiveEntitlement(
                entitlement_id="entl_health_pro",
                environment="production",
                expires_at_ms=int((timezone.now() + timedelta(days=30)).timestamp() * 1000),
                started_at_ms=None,
                product_id="health_monthly",
                store="app_store",
                period_type="normal",
                will_renew=True,
                original_transaction_id="transaction-1",
            )
        ]
        result = RevenueCatSubscriptionSyncService.sync_user(user=self.user, reason="test")
        self.assertTrue(result["is_pro"])
        self.assertTrue(RevenueCatEntitlement.objects.filter(user=self.user, status="active", environment="production").exists())

    @override_settings(REVENUECAT_AUTHORIZATION_ENVIRONMENTS=("production",))
    def test_sandbox_snapshot_does_not_grant_pro_in_production(self):
        RevenueCatEntitlement.objects.create(
            user=self.user,
            entitlement_identifier="健康Pro",
            environment="sandbox",
            status="active",
            original_transaction_id="sandbox-transaction-1",
            expires_at=timezone.now() + timedelta(days=1),
        )
        RevenueCatSubscriptionOwnership.objects.create(
            user=self.user,
            store="app_store",
            environment="sandbox",
            original_transaction_id="sandbox-transaction-1",
            owner_account_fingerprint="test",
            first_bound_at=timezone.now(),
            last_verified_at=timezone.now(),
        )
        self.assertFalse(ProEntitlementResolver.is_pro_user(user=self.user))

    def test_manual_trial_remains_effective_without_revenuecat_snapshot(self):
        TrialApplication.objects.create(
            user=self.user,
            status=TrialApplication.Status.ACTIVE,
            grant_source=TrialApplication.GrantSource.MANUAL,
            started_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=1),
        )
        result = ProEntitlementResolver.resolve(user=self.user)
        self.assertTrue(result["is_pro"])
        self.assertTrue(next(source for source in result["sources"] if source["type"] == "manual")["active"])

    @patch("subscriptions.services.subscription_sync_service.RevenueCatClient.get_active_entitlements")
    def test_same_transaction_cannot_bind_to_another_account(self, mock_active):
        mock_active.return_value = [
            ActiveEntitlement(
                entitlement_id="entl_health_pro",
                environment="production",
                expires_at_ms=int((timezone.now() + timedelta(days=30)).timestamp() * 1000),
                started_at_ms=None,
                product_id="health_monthly",
                store="app_store",
                period_type="normal",
                will_renew=True,
                original_transaction_id="transaction-owned-by-first-user",
            )
        ]
        RevenueCatSubscriptionSyncService.sync_user(user=self.user, reason="purchase")
        second_user = get_user_model().objects.create_user(username="subscription-test-2", email="subscription2@example.com")
        with self.assertRaises(RevenueCatProviderError) as error:
            RevenueCatSubscriptionSyncService.sync_user(user=second_user, reason="restore")
        self.assertEqual(error.exception.code, "subscription_sync_failed")
        self.assertEqual(RevenueCatOwnershipConflictEvent.objects.count(), 1)

    def test_expired_snapshot_is_not_pro(self):
        ownership = RevenueCatSubscriptionOwnership.objects.create(
            user=self.user,
            store="app_store",
            environment="production",
            original_transaction_id="expired-transaction",
            owner_account_fingerprint="test",
            first_bound_at=timezone.now(),
            last_verified_at=timezone.now(),
        )
        RevenueCatEntitlement.objects.create(
            user=self.user,
            entitlement_identifier="健康Pro",
            environment="production",
            status="active",
            original_transaction_id=ownership.original_transaction_id,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.assertFalse(ProEntitlementResolver.is_pro_user(user=self.user))

    @override_settings(REVENUECAT_PROJECT_ID="project", REVENUECAT_SECRET_API_KEY="secret")
    def test_revenuecat_subscription_details_preserve_sandbox_environment(self):
        client = RevenueCatClient()
        with patch.object(
            client,
            "_get_list",
            return_value=[
                {
                    "gives_access": True,
                    "current_period_ends_at": "1790148000000",
                    "current_period_starts_at": "1790147700000",
                    "store": "app_store",
                    "status": "trial",
                    "auto_renewal_status": "will_renew",
                    "store_subscription_identifier": "sandbox-transaction",
                    "entitlements": {
                        "items": [
                            {
                                "id": "entl_health_pro",
                                "state": "active",
                                "products": {"items": [{"store_identifier": "health_yearly_99_intro3days_free"}]},
                            }
                        ]
                    },
                }
            ],
        ):
            details = client._get_entitlement_details(customer_id="1058", environment="sandbox")
        self.assertEqual(details["entl_health_pro"].environment, "sandbox")

    @patch("subscriptions.views.RevenueCatSubscriptionSyncService.sync_user")
    def test_sync_idempotency_replays_success_without_second_provider_call(self, mock_sync):
        mock_sync.return_value = {"is_pro": False, "effective_source": "none", "sources": []}
        client = APIClient()
        client.force_authenticate(user=self.user)
        first = client.post("/api/v1/subscriptions/revenuecat/sync/", HTTP_IDEMPOTENCY_KEY="sync-key-1")
        second = client.post("/api/v1/subscriptions/revenuecat/sync/", HTTP_IDEMPOTENCY_KEY="sync-key-1")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(mock_sync.call_count, 1)

    @patch("subscriptions.views.RevenueCatSubscriptionSyncService.sync_user")
    def test_sync_idempotency_replays_ownership_conflict_as_error(self, mock_sync):
        mock_sync.side_effect = RevenueCatProviderError("subscription_sync_failed", retryable=False)
        client = APIClient()
        client.force_authenticate(user=self.user)
        first = client.post("/api/v1/subscriptions/revenuecat/sync/", HTTP_IDEMPOTENCY_KEY="sync-key-2")
        second = client.post("/api/v1/subscriptions/revenuecat/sync/", HTTP_IDEMPOTENCY_KEY="sync-key-2")
        self.assertEqual(first.status_code, 409)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.data["code"], 42024)
        self.assertEqual(mock_sync.call_count, 1)

    @override_settings(REVENUECAT_WEBHOOK_AUTHORIZATION="test-webhook-secret")
    def test_webhook_is_idempotent(self):
        client = APIClient()
        payload = {"event": {"id": "evt_1", "type": "INITIAL_PURCHASE", "app_user_id": str(self.user.id), "environment": "production"}}
        with patch("subscriptions.views.process_revenuecat_webhook_event.delay"):
            first = client.post("/api/v1/integrations/revenuecat/webhook/", payload, format="json", HTTP_AUTHORIZATION="test-webhook-secret")
            second = client.post("/api/v1/integrations/revenuecat/webhook/", payload, format="json", HTTP_AUTHORIZATION="test-webhook-secret")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(RevenueCatWebhookEvent.objects.filter(event_id="evt_1").count(), 1)
