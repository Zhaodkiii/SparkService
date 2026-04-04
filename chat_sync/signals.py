from django.db.models.signals import post_save
from django.dispatch import receiver

from chat_sync.events import ChatSyncNotifier
from chat_sync.models import ChatMessage


@receiver(post_save, sender=ChatMessage)
def on_chat_message_saved(sender, instance: ChatMessage, **kwargs):
    ChatSyncNotifier.notify_user_sync(
        user_id=instance.user_id,
        cursor=instance.server_updated_at.isoformat(),
        message_ids=[instance.server_message_id],
    )
