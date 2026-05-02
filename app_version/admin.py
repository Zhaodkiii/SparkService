from django.contrib import admin

from app_version.models import AppVersionConfig, UpdateActionLog, VersionCheckLog


@admin.register(AppVersionConfig)
class AppVersionConfigAdmin(admin.ModelAdmin):
    list_display = ("platform", "bundle_id", "channel", "latest_version", "latest_build", "is_active", "updated_at")
    list_filter = ("platform", "channel", "is_active", "enable_gradual_release")
    search_fields = ("bundle_id", "latest_version", "update_title")


@admin.register(VersionCheckLog)
class VersionCheckLogAdmin(admin.ModelAdmin):
    list_display = ("platform", "bundle_id", "current_version", "has_update", "force_update", "device_id", "checked_at")
    list_filter = ("platform", "channel", "has_update", "force_update")
    search_fields = ("bundle_id", "device_id", "current_version", "request_id")


@admin.register(UpdateActionLog)
class UpdateActionLogAdmin(admin.ModelAdmin):
    list_display = ("action", "platform", "device_id", "user", "action_at")
    list_filter = ("action", "platform")
    search_fields = ("device_id", "request_id")
