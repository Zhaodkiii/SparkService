from __future__ import annotations

from django.db import transaction

from subscriptions.models import RevenueCatCustomerAlias, RevenueCatCustomerIdentity, RevenueCatWebhookEvent
from subscriptions.services.identity_service import RevenueCatIdentityService


class RevenueCatWebhookInboxService:
    _INDEXED_IDENTIFIER_MAX_LENGTH = 255

    @staticmethod
    @transaction.atomic
    def enqueue(*, event: dict) -> tuple[RevenueCatWebhookEvent, bool]:
        event_id = str(event.get("id") or "").strip()
        if not event_id:
            raise ValueError("missing_event_id")
        row, created = RevenueCatWebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={
                "event_type": str(event.get("type") or ""),
                # Retain the complete value in payload; this indexed query hint must
                # stay MySQL-safe under utf8mb4.
                "app_user_id": str(event.get("app_user_id") or "")[:RevenueCatWebhookInboxService._INDEXED_IDENTIFIER_MAX_LENGTH],
                "environment": str(event.get("environment") or "").lower(),
                "event_timestamp_ms": int(event.get("event_timestamp_ms") or event.get("event_timestamp") or 0),
                "payload": event,
            },
        )
        return row, created

    @staticmethod
    @transaction.atomic
    def match_user(*, row: RevenueCatWebhookEvent):
        users = RevenueCatWebhookInboxService.match_users(row=row)
        return users[0] if users else None

    @staticmethod
    @transaction.atomic
    def match_users(*, row: RevenueCatWebhookEvent) -> list:
        event = row.payload if isinstance(row.payload, dict) else {}
        candidates = [event.get("app_user_id"), event.get("original_app_user_id")]
        aliases = event.get("aliases") or []
        if isinstance(aliases, list):
            candidates.extend(aliases)
        normalized = [
            value
            for value in (str(raw).strip() for raw in candidates)
            if value and len(value) <= RevenueCatWebhookInboxService._INDEXED_IDENTIFIER_MAX_LENGTH
        ]
        identities = list(RevenueCatCustomerIdentity.objects.select_for_update().filter(app_user_id__in=normalized))
        alias_identities = list(
            RevenueCatCustomerAlias.objects.select_related("identity").filter(alias__in=normalized).values_list("identity_id", flat=True)
        )
        if alias_identities:
            identities.extend(
                RevenueCatCustomerIdentity.objects.select_for_update().filter(id__in=alias_identities)
            )
        unique = {identity.id: identity for identity in identities}.values()
        users = []
        for identity in unique:
            RevenueCatIdentityService.remember_aliases(identity=identity, aliases=normalized, source=RevenueCatCustomerAlias.Source.WEBHOOK)
            users.append(identity.user)
        if users:
            row.matched_user = users[0]
            row.save(update_fields=["matched_user"])
        return users
