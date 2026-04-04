from django.apps import AppConfig


class ChatSyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chat_sync"

    def ready(self):
        from chat_sync import signals  # noqa: F401
