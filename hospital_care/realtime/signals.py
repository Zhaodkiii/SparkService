from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from chat_sync.models import ChatMessage
from hospital_care.realtime.dispatch import dispatch_doctor_conversation_hint


@receiver(post_save, sender=ChatMessage)
def on_chat_message_saved_notify_doctor(sender, instance: ChatMessage, **kwargs):
    # BACKOFFICE-CONVERSATION-000002：闭包只捕获已固化的标量值，
    # 与患者账号同步通知并存，事务提交成功后才分发医生工作台提示。
    thread_id = instance.thread_id
    message_id = instance.server_message_id
    cursor = instance.server_updated_at.isoformat()
    transaction.on_commit(
        lambda: dispatch_doctor_conversation_hint(
            thread_id=thread_id,
            message_id=message_id,
            cursor=cursor,
        )
    )
