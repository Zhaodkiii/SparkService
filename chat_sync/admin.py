from django.contrib import admin

from chat_sync.models import ChatMessage, ChatThread


@admin.register(ChatThread)
class ChatThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "scenario", "updated_at", "is_deleted")
    list_filter = ("scenario", "is_deleted")
    search_fields = ("id", "user__username", "title")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "thread", "user", "role", "kind", "delivery_state", "server_updated_at")
    list_filter = ("role", "kind", "delivery_state", "tombstone")
    search_fields = ("server_message_id", "client_message_id")
