from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings


class RevenueCatProviderError(Exception):
    def __init__(self, code: str, *, retryable: bool):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class ActiveEntitlement:
    entitlement_id: str
    environment: str
    expires_at_ms: int | None
    started_at_ms: int | None
    product_id: str
    store: str
    period_type: str
    will_renew: bool
    original_transaction_id: str


class RevenueCatClient:
    """Server-only RevenueCat API v2 reader. Never expose its credentials to a client."""

    def __init__(self):
        self.base_url = str(getattr(settings, "REVENUECAT_API_BASE_URL", "https://api.revenuecat.com/v2")).rstrip("/")
        self.project_id = str(getattr(settings, "REVENUECAT_PROJECT_ID", "")).strip()
        self.api_key = str(getattr(settings, "REVENUECAT_SECRET_API_KEY", "")).strip()
        self.timeout_seconds = int(getattr(settings, "REVENUECAT_SYNC_TIMEOUT_SECONDS", 8))

    def get_active_entitlements(
        self,
        *,
        customer_id: str,
        environment: str = "production",
    ) -> list[ActiveEntitlement]:
        if not self.project_id or not self.api_key:
            raise RevenueCatProviderError("revenuecat_not_configured", retryable=False)
        active_items = self._get_list(
            path=f"/projects/{self.project_id}/customers/{customer_id}/active_entitlements",
        )
        # API v2 active_entitlements does not expose an environment. Verify every
        # candidate against the environment-filtered subscriptions resource.
        environment_details = self._get_entitlement_details(
            customer_id=customer_id,
            environment=environment,
        )
        result: list[ActiveEntitlement] = []
        for item in active_items:
            entitlement_id = str(item.get("entitlement_id") or "")
            detail = environment_details.get(entitlement_id)
            if detail is None:
                continue
            result.append(
                ActiveEntitlement(
                    entitlement_id=entitlement_id,
                    environment=str(environment).lower(),
                    expires_at_ms=self._integer_or_none(item.get("expires_at")) or detail.expires_at_ms,
                    started_at_ms=detail.started_at_ms,
                    product_id=detail.product_id,
                    store=detail.store,
                    period_type=detail.period_type,
                    will_renew=detail.will_renew,
                    original_transaction_id=detail.original_transaction_id,
                )
            )
        return result

    def _get_list(self, *, path: str, params: dict[str, str | int] | None = None) -> list[dict[str, Any]]:
        url = f"{self.base_url}{path}"
        try:
            response = httpx.get(
                url,
                headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
                timeout=self.timeout_seconds,
                params=params,
            )
        except httpx.TimeoutException as exc:
            raise RevenueCatProviderError("revenuecat_timeout", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise RevenueCatProviderError("revenuecat_network_error", retryable=True) from exc

        if response.status_code == 404:
            return []
        if response.status_code in {408, 423, 429, 500, 502, 503, 504}:
            raise RevenueCatProviderError("revenuecat_unavailable", retryable=True)
        if response.status_code >= 400:
            raise RevenueCatProviderError("revenuecat_rejected", retryable=False)
        try:
            body = response.json()
        except ValueError as exc:
            raise RevenueCatProviderError("revenuecat_invalid_response", retryable=True) from exc
        items = body.get("items", []) if isinstance(body, dict) else []
        if not isinstance(items, list):
            raise RevenueCatProviderError("revenuecat_invalid_response", retryable=True)
        return [item for item in items if isinstance(item, dict)]

    def _get_entitlement_details(
        self,
        *,
        customer_id: str,
        environment: str,
    ) -> dict[str, ActiveEntitlement]:
        subscriptions = self._get_list(
            path=f"/projects/{self.project_id}/customers/{customer_id}/subscriptions",
            params={"environment": environment, "limit": 100},
        )
        details: dict[str, ActiveEntitlement] = {}
        for subscription in subscriptions:
            if not bool(subscription.get("gives_access")):
                continue
            entitlements = subscription.get("entitlements") or {}
            rows = entitlements.get("items") if isinstance(entitlements, dict) else []
            if not isinstance(rows, list):
                continue
            for entitlement in rows:
                if not isinstance(entitlement, dict) or entitlement.get("state") != "active":
                    continue
                entitlement_id = str(entitlement.get("id") or "")
                if not entitlement_id:
                    continue
                products = entitlement.get("products") or {}
                # RevenueCat may return `products: {items: null}` when a
                # subscription has no product detail in the selected environment.
                # Missing product metadata must not make the whole entitlement
                # synchronization fail; the subscription can still grant access.
                product_rows = (
                    products.get("items") or []
                    if isinstance(products, dict)
                    else []
                )
                product = next((row for row in product_rows if isinstance(row, dict)), {})
                details[entitlement_id] = ActiveEntitlement(
                    entitlement_id=entitlement_id,
                    environment=str(environment).lower(),
                    expires_at_ms=self._integer_or_none(subscription.get("current_period_ends_at") or subscription.get("ends_at")),
                    started_at_ms=self._integer_or_none(subscription.get("current_period_starts_at") or subscription.get("starts_at")),
                    product_id=str(product.get("store_identifier") or product.get("id") or ""),
                    store=str(subscription.get("store") or ""),
                    period_type=str(subscription.get("status") or ""),
                    will_renew=str(subscription.get("auto_renewal_status") or "") == "will_renew",
                    original_transaction_id=str(subscription.get("store_subscription_identifier") or ""),
                )
        return details

    @staticmethod
    def _integer_or_none(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
