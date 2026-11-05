from django.contrib import admin
from .models import ProductionPolicy, ProductionWindow, ProductionTask, ProductionLedger


@admin.register(ProductionPolicy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "effective_at", "short_limit", "weekly_limit", "enabled")
    def has_change_permission(self, request, obj=None):
        return obj is None
    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProductionTask)
class TaskAdmin(ReadOnlyAdmin):
    list_display = ("id", "account", "state", "version", "expires_at")
    list_filter = ("state",)
    search_fields = ("id", "account__username")


@admin.register(ProductionWindow)
class WindowAdmin(ReadOnlyAdmin):
    list_display = ("account", "kind", "starts_at", "ends_at", "limit", "used", "reserved")


@admin.register(ProductionLedger)
class LedgerAdmin(ReadOnlyAdmin):
    list_display = ("task", "event", "reservation_id", "actor", "created_at")
