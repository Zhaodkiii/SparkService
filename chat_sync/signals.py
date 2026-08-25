from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from chat_sync.events import ChatSyncNotifier
from chat_sync.models import ChatMessage


@receiver(post_save, sender=ChatMessage)
def on_chat_message_saved(sender, instance: ChatMessage, **kwargs):
    user_id = instance.user_id
    cursor = instance.server_updated_at.isoformat()
    message_id = instance.server_message_id
    transaction.on_commit(
        lambda: ChatSyncNotifier.notify_user_sync(
            user_id=user_id,
            cursor=cursor,
            message_ids=[message_id],
        )
    )
