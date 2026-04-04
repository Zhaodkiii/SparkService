from django.contrib import admin

from file_manager.models import ManagedFile


@admin.register(ManagedFile)
class ManagedFileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "original_name",
        "file_size",
        "mime_type",
        "business_type",
        "business_id",
        "is_public",
        "is_deleted",
        "created_at",
    )
    list_filter = ("is_public", "is_deleted", "business_type")
    search_fields = ("original_name", "file_uuid", "business_type", "business_id", "user__username")
