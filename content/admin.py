from django.contrib import admin

from content.models import (
    ContentArticle,
    ContentArticleOperationLog,
    ContentArticleReadEvent,
    ContentArticleTag,
    ContentArticleVersion,
    ContentCategory,
    ContentTag,
)


@admin.register(ContentArticle)
class ContentArticleAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "locale", "status", "visibility", "category", "published_at", "updated_at")
    list_filter = ("status", "visibility", "locale", "category")
    search_fields = ("title", "slug", "summary")


admin.site.register(ContentCategory)
admin.site.register(ContentTag)
admin.site.register(ContentArticleTag)
admin.site.register(ContentArticleVersion)
admin.site.register(ContentArticleOperationLog)
admin.site.register(ContentArticleReadEvent)
