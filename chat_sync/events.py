from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging

logger = logging.getLogger("chat_sync.sync")


class ChatSyncNotifier:
    @staticmethod
    def user_group(user_id: int) -> str:
        return f"user_{user_id}"

    @staticmethod
    def device_session_group(session_id: int) -> str:
        return f"device_session_{int(session_id)}"

    @staticmethod
    def web_session_group(session_id: str) -> str:
        return f"web_session_{str(session_id).replace('-', '')}"

    @classmethod
    def notify_web_session_invalidated(cls, session_id: str, reason: str = "revoked"):
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.warning("chat web session invalidation skipped channel_layer unavailable session_id=%s", session_id)
            return
        async_to_sync(channel_layer.group_send)(
            cls.web_session_group(session_id),
            {"type": "chat.web.session.invalidated", "reason": reason},
        )
        logger.info("chat web session invalidated session_id_tail=%s reason=%s", str(session_id)[-8:], reason)

    @classmethod
    def notify_device_session_invalidated(cls, session_id: int, reason: str = "replaced"):
        """Close only sockets authenticated by the replaced mobile session."""
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.warning("chat sync session invalidation skipped channel_layer unavailable session_id=%s", session_id)
            return
        async_to_sync(channel_layer.group_send)(
            cls.device_session_group(session_id),
            {
                "type": "chat.device.session.invalidated",
                "reason": reason,
            },
        )
        logger.info("chat sync device session invalidated session_id=%s reason=%s", session_id, reason)

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
