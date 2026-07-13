from django.contrib import admin

from notification_center.models import (
    ChannelDelivery,
    ChannelTemplateVersion,
    ContactEndpoint,
    DeliveryAttempt,
    NotificationAuditLog,
    NotificationBusinessScene,
    NotificationCampaign,
    NotificationIntent,
    NotificationMessage,
    NotificationOutbox,
    NotificationPreference,
    NotificationSuppression,
    NotificationTemplate,
    NotificationTemplateVersion,
    NotificationTopic,
    ProviderEvent,
)


@admin.register(NotificationBusinessScene)
class NotificationBusinessSceneAdmin(admin.ModelAdmin):
    list_display = ("key", "display_name", "domain", "business_type", "category", "severity", "status", "updated_at")
    search_fields = ("key", "display_name", "domain", "business_type", "event_name")
    list_filter = ("domain", "category", "severity", "status")


@admin.register(NotificationTopic)
class NotificationTopicAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "category", "requires_user", "is_active", "updated_at")
    search_fields = ("key", "name")
    list_filter = ("category", "requires_user", "is_active")


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "key", "name", "topic_key", "is_active", "updated_at")
    search_fields = ("key", "name", "description")
    list_filter = ("topic_key", "is_active")


@admin.register(NotificationTemplateVersion)
class NotificationTemplateVersionAdmin(admin.ModelAdmin):
    list_display = ("id", "template", "version", "locale", "status", "updated_at")
    list_filter = ("locale", "status")


@admin.register(ChannelTemplateVersion)
class ChannelTemplateVersionAdmin(admin.ModelAdmin):
    list_display = ("id", "template_version", "channel", "provider", "provider_template_code", "updated_at")
    list_filter = ("channel", "provider")


@admin.register(NotificationIntent)
class NotificationIntentAdmin(admin.ModelAdmin):
    list_display = ("id", "business_scene", "business_type", "business_id", "status", "priority", "created_at")
    search_fields = ("topic_key", "business_scene", "business_type", "business_id", "idempotency_key", "event_id")
    list_filter = ("status", "topic_key", "business_scene", "business_domain")


@admin.register(NotificationCampaign)
class NotificationCampaignAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "status", "target_count", "success_count", "failure_count", "created_at")
    search_fields = ("name", "request_id", "task_id")
    list_filter = ("status",)


@admin.register(NotificationMessage)
class NotificationMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "campaign", "user", "channel", "status", "sent_at", "created_at")
    search_fields = ("title", "body", "request_id", "provider_message_id")
    list_filter = ("channel", "status")


@admin.register(ContactEndpoint)
class ContactEndpointAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "channel", "address_masked", "is_verified", "is_active", "last_seen")
    search_fields = ("address_hmac", "address_masked")
    list_filter = ("channel", "is_verified", "is_active")


@admin.register(ChannelDelivery)
class ChannelDeliveryAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "channel", "provider", "status", "attempt_count", "updated_at")
    list_filter = ("channel", "status", "provider")


@admin.register(DeliveryAttempt)
class DeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "delivery", "attempt_no", "outcome", "duration_ms", "created_at")
    list_filter = ("outcome",)


@admin.register(ProviderEvent)
class ProviderEventAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "external_event_id", "normalized_type", "occurred_at")
    list_filter = ("provider", "normalized_type")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "topic_key", "channel", "enabled", "updated_at")
    list_filter = ("channel", "enabled")


@admin.register(NotificationSuppression)
class NotificationSuppressionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "channel", "reason", "expires_at", "created_at")
    list_filter = ("channel", "reason")


@admin.register(NotificationOutbox)
class NotificationOutboxAdmin(admin.ModelAdmin):
    list_display = ("id", "aggregate_type", "aggregate_id", "event_type", "status", "attempts", "created_at")
    list_filter = ("status", "aggregate_type", "event_type")


@admin.register(NotificationAuditLog)
class NotificationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "actor_user", "action", "target_type", "target_id", "request_id", "created_at")
    search_fields = ("action", "target_type", "target_id", "request_id")
