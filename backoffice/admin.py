from django.contrib import admin

from backoffice.models import AdminAuditLog, AdminPermission, AdminPermissionPreset, AdminRole, AdminRolePermission, AdminUserRole


@admin.register(AdminRole)
class AdminRoleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(AdminPermission)
class AdminPermissionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "permission_type", "method", "path", "is_active")
    list_filter = ("permission_type", "is_active")
    search_fields = ("name", "code", "path")


@admin.register(AdminRolePermission)
class AdminRolePermissionAdmin(admin.ModelAdmin):
    list_display = ("id", "role", "permission", "created_at")
    search_fields = ("role__name", "permission__code")


@admin.register(AdminUserRole)
class AdminUserRoleAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "role", "created_at")
    search_fields = ("user__username", "user__email", "role__name")


@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "action", "resource_type", "status_code", "path", "created_at")
    list_filter = ("status_code", "resource_type")
    search_fields = ("action", "path", "request_id", "resource_id")
    readonly_fields = (
        "user",
        "action",
        "resource_type",
        "resource_id",
        "method",
        "path",
        "status_code",
        "request_id",
        "ip_address",
        "user_agent",
        "request_payload",
        "response_payload",
        "created_at",
    )


@admin.register(AdminPermissionPreset)
class AdminPermissionPresetAdmin(admin.ModelAdmin):
    list_display = ("id", "key", "created_at")
