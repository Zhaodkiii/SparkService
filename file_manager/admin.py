from django.contrib import admin

from file_manager.models import ManagedFile, ManagedFileBusinessRelation


class ManagedFileBusinessRelationInline(admin.TabularInline):
    model = ManagedFileBusinessRelation
    extra = 0
    fields = ("business_type", "business_id", "created_at")
    readonly_fields = ("created_at",)


@admin.register(ManagedFile)
class ManagedFileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "original_name",
        "file_size",
        "mime_type",
        "is_public",
        "is_deleted",
        "created_at",
    )
    list_filter = ("is_public", "is_deleted", "business_relations__business_type")
    search_fields = (
        "original_name",
        "file_uuid",
        "business_relations__business_type",
        "business_relations__business_id",
        "user__username",
    )
    inlines = (ManagedFileBusinessRelationInline,)


@admin.register(ManagedFileBusinessRelation)
class ManagedFileBusinessRelationAdmin(admin.ModelAdmin):
    list_display = ("id", "file", "user", "business_type", "business_id", "created_at")
    list_filter = ("business_type", "created_at")
    search_fields = ("file__original_name", "business_type", "business_id", "user__username")
