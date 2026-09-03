from __future__ import annotations

import logging
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

logger = logging.getLogger("hospital_care.realtime")


class DoctorConversationNotifier:
    """BACKOFFICE-CONVERSATION-000002：医生工作台实时提示分发器。

    事件只携带可关联元数据（event_id/thread_id/message_ids/时间戳），
    不包含消息正文、患者资料或任何可直接展示的医疗信息。
    """

    @staticmethod
    def doctor_group(doctor_id) -> str:
        return f"hospital_doctor_{doctor_id}"

    @classmethod
    def notify_conversation_updated(cls, *, doctor_id, thread_id, message_ids: list[str], cursor: str) -> None:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.warning(
                "doctor conversation notify skipped channel_layer unavailable doctor_id=%s thread_id=%s",
                doctor_id,
                thread_id,
            )
            return
        event = {
            "type": "hospital.conversation.updated",
            "payload_version": 1,
            "event_id": str(uuid.uuid4()),
            "thread_id": str(thread_id),
            "message_ids": [str(item) for item in message_ids],
            "cursor": cursor,
            "emitted_at": timezone.now().isoformat(),
            "change_kind": "message_created",
        }
        try:
            async_to_sync(channel_layer.group_send)(
                cls.doctor_group(doctor_id),
                {"type": "hospital.conversation.updated", "event": event},
            )
        except Exception:
            # 实时通道故障不影响消息主写入流程。
            logger.exception(
                "doctor conversation notify failed doctor_id=%s thread_id=%s event_id=%s",
                doctor_id,
                thread_id,
                event["event_id"],
            )
            return
        logger.info(
            "doctor conversation notified doctor_id=%s thread_id=%s message_count=%s event_id=%s",
            doctor_id,
            thread_id,
            len(event["message_ids"]),
            event["event_id"],
        )
