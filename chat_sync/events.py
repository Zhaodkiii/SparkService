from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone
import logging
import uuid

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
    def notify_user_sync(cls, user_id: int, cursor: str, message_ids: list[str], thread_id=None):
        """CHAT-000056：实时变化提示（hint），不携带消息正文。

        thread_id 存在时按 v2 契约下发（event_id/thread_id/emitted_at），
        客户端据此做会话定向增量拉取；无 thread_id 的旧调用方保持 v1，
        新客户端收到 v1 事件时执行账号级全局补偿。
        """
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.warning("chat sync notify skipped channel_layer unavailable user_id=%s", user_id)
            return

        event = {
            "type": "chat.sync.updated",
            "cursor": cursor,
            "message_ids": message_ids,
        }
        if thread_id is not None:
            event.update({
                "payload_version": 2,
                "event_id": str(uuid.uuid4()),
                "thread_id": str(thread_id),
                "emitted_at": timezone.now().isoformat(),
            })
        else:
            event["payload_version"] = 1

        async_to_sync(channel_layer.group_send)(
            cls.user_group(user_id),
            {
                "type": "chat.sync.updated",
                "event": event,
            },
        )
        logger.info(
            "chat sync notified user_id=%s cursor=%s message_count=%s thread_id=%s",
            user_id,
            cursor,
            len(message_ids),
            thread_id or "-",
        )
