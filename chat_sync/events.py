from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging

logger = logging.getLogger("chat_sync.sync")


class ChatSyncNotifier:
    @staticmethod
    def user_group(user_id: int) -> str:
        return f"user_{user_id}"

    @classmethod
    def notify_user_sync(cls, user_id: int, cursor: str, message_ids: list[str]):
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.warning("chat sync notify skipped channel_layer unavailable user_id=%s", user_id)
            return

        async_to_sync(channel_layer.group_send)(
            cls.user_group(user_id),
            {
                "type": "chat.sync.updated",
                "event": {
                    "type": "chat.sync.updated",
                    "cursor": cursor,
                    "message_ids": message_ids,
                },
            },
        )
        logger.info("chat sync notified user_id=%s cursor=%s message_count=%s", user_id, cursor, len(message_ids))
