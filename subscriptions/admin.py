from django.contrib import admin

from subscriptions.models import (
    RevenueCatCustomerAlias,
    RevenueCatCustomerIdentity,
    RevenueCatEntitlement,
    RevenueCatOwnershipConflictEvent,
    RevenueCatSubscriptionOwnership,
    RevenueCatSyncRequest,
    RevenueCatWebhookEvent,
)


@admin.register(RevenueCatCustomerIdentity)
class RevenueCatCustomerIdentityAdmin(admin.ModelAdmin):
    list_display = ("user", "app_user_id", "last_successful_sync_at", "last_sync_error_code")
    search_fields = ("app_user_id", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(RevenueCatCustomerAlias)
class RevenueCatCustomerAliasAdmin(admin.ModelAdmin):
    list_display = ("alias", "identity", "source", "last_seen_at")
    search_fields = ("alias", "identity__app_user_id")
    readonly_fields = ("first_seen_at", "last_seen_at")


@admin.register(RevenueCatEntitlement)
class RevenueCatEntitlementAdmin(admin.ModelAdmin):
    list_display = ("user", "entitlement_identifier", "environment", "status", "expires_at", "last_synced_at")
    list_filter = ("environment", "status")
    search_fields = ("user__email", "product_id", "original_transaction_id")
    readonly_fields = ("last_synced_at", "provider_updated_at")


@admin.register(RevenueCatSubscriptionOwnership)
class RevenueCatSubscriptionOwnershipAdmin(admin.ModelAdmin):
    list_display = ("user", "store", "environment", "state", "first_product_id", "first_bound_at", "last_verified_at")
    list_filter = ("environment", "state", "store")
    search_fields = ("original_transaction_id", "owner_account_fingerprint", "user__email")
    readonly_fields = ("original_transaction_id", "owner_account_fingerprint", "created_at", "updated_at")


@admin.register(RevenueCatOwnershipConflictEvent)
class RevenueCatOwnershipConflictEventAdmin(admin.ModelAdmin):
    list_display = ("attempted_user", "ownership", "trigger", "environment", "transaction_suffix", "occurred_at")
    list_filter = ("environment", "trigger")
    search_fields = ("transaction_suffix", "request_id")
    readonly_fields = ("ownership", "attempted_user", "trigger", "store", "environment", "transaction_suffix", "request_id", "occurred_at")


@admin.register(RevenueCatSyncRequest)
class RevenueCatSyncRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "idempotency_key", "status", "response_status", "created_at")
    search_fields = ("idempotency_key", "user__email")
    readonly_fields = ("response_payload", "created_at", "updated_at")


@admin.register(RevenueCatWebhookEvent)
class RevenueCatWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "environment", "process_status", "attempt_count", "received_at")
    list_filter = ("process_status", "environment", "event_type")
    search_fields = ("event_id", "app_user_id")
    readonly_fields = ("payload", "received_at", "processed_at")
