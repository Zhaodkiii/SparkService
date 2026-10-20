"""Transactional reminders share the existing notification center, not marketing campaigns."""
import logging
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from notification_center.models import NotificationIntent,NotificationOutbox,NotificationTemplate
from notification_center.services import NotificationCenterService

MESSAGES={
 'pending_reminder':('你的定制还有待查看的更新','open_customization'),
 'info_requested':('你的定制需要补充资料，请打开查看','open_customization_info'),
 'due_changed':('你的定制交付时间有更新','open_customization'),
 'rejected':('你的定制需求处理结果已更新','open_customization'),
 'cancelled':('你的定制需求状态有更新','open_customization'),
 'delivered':('你的专属手帐已完成，快来查看吧','open_customization_delivery'),
 'redelivered':('你的专属手帐已更新，请查看新版','open_customization_delivery'),
 'delivery_withdrawn':('你的定制成品状态有调整，请查看说明','open_customization'),
 'delivery_rolled_back':('你的定制成品版本有更新','open_customization_delivery')}

def enqueue(event):
    obj=event.request
    scene=NotificationCenterService.ensure_business_scene('diary.customization.'+event.action,topic_key='diary.customization')
    template=NotificationTemplate.objects.filter(key=scene.default_template_key,is_active=True).first()
    version=template.versions.filter(status='published').order_by('-version').first() if template else None
    key=f'custom:{event.pk}:{obj.owner_id}:apns'
    intent,_=NotificationIntent.objects.get_or_create(idempotency_key=key,defaults=dict(
        topic_key='diary.customization',business_scene=scene.key,business_domain='diary',business_type='diary.customization',
        business_reference_type='customization_request',business_id=str(obj.pk),subject_type='user',subject_id=str(obj.owner_id),
        event_id=str(event.pk),occurred_at=event.created_at,expires_at=timezone.now()+timedelta(hours=24),
        template_key=template.key if template else '',template_version=version,
        scene_contract_version=1,scene_snapshot=NotificationCenterService._scene_snapshot(scene),
        routing={'mode':'parallel','steps':[{'channel':'apns','required':False}]},source='diary_customizations'))
    NotificationOutbox.objects.get_or_create(idempotency_key=key,defaults=dict(aggregate_type='notification_intent',aggregate_id=str(intent.pk),
        event_type='notification.diary_customization.dispatch',payload={'intent_id':intent.pk,'event_id':str(event.pk)},available_at=timezone.now()))
    def wake():
        try:
            from notification_center.tasks import relay_notification_outbox_task
            relay_notification_outbox_task.delay()
        except Exception:
            logging.getLogger(__name__).warning('custom notification wake deferred; persisted outbox will relay')
    transaction.on_commit(wake)
