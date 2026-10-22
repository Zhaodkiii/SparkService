import logging
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from notification_center.models import NotificationIntent,NotificationOutbox
from notification_center.services import NotificationCenterService

def enqueue(message):
    scene=NotificationCenterService.ensure_business_scene('support.feedback.updated',topic_key='support.feedback')
    key=f'support:{message.pk}:{message.ticket.owner_id}:apns'
    intent,_=NotificationIntent.objects.get_or_create(idempotency_key=key,defaults=dict(
        topic_key='support.feedback',business_scene=scene.key,business_domain='support',business_type='support.feedback',
        business_reference_type='support_ticket',business_id=str(message.ticket_id),subject_type='user',subject_id=str(message.ticket.owner_id),
        event_id=str(message.pk),occurred_at=message.created_at,expires_at=timezone.now()+timedelta(hours=24),
        scene_contract_version=1,scene_snapshot=NotificationCenterService._scene_snapshot(scene),
        routing={'mode':'parallel','steps':[{'channel':'apns','required':False}]},source='support_center'))
    NotificationOutbox.objects.get_or_create(idempotency_key=key,defaults=dict(aggregate_type='notification_intent',aggregate_id=str(intent.pk),
        event_type='notification.support.dispatch',payload={'intent_id':intent.pk,'event_id':str(message.pk)},available_at=timezone.now()))
    def wake():
        try:
            from notification_center.tasks import relay_notification_outbox_task
            relay_notification_outbox_task.delay()
        except Exception:logging.getLogger(__name__).warning('support notification wake deferred to persisted outbox')
    transaction.on_commit(wake)
