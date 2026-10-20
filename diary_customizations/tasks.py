from datetime import timedelta
import random
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from notification_center.models import NotificationIntent,NotificationOutbox,NotificationMessage,NotificationRecipientMessage,ChannelDelivery,NotificationPreference
from notification_center.services import NotificationCenterService,_SendResult
from accounts.services.device_session_service import DeviceSessionService
from accounts.infrastructure.apns_provider import APNsProvider
from .models import Event
from .notifications import MESSAGES

@shared_task
def dispatch_notification(intent_id,event_id):
    # Reserve a lease in existing delivery state. Never hold DB locks during network I/O.
    with transaction.atomic():
        intent=NotificationIntent.objects.select_for_update().get(pk=intent_id)
        box=NotificationOutbox.objects.select_for_update().get(idempotency_key=intent.idempotency_key)
        if box.status=='processed': return
        event=Event.objects.select_related('request__owner').get(pk=event_id)
        obj=event.request;now=timezone.now();reason=''
        if obj.deleted_at or not obj.owner.is_active: reason='unavailable'
        elif intent.expires_at and intent.expires_at<=now: reason='expired'
        elif obj.last_read_sequence>=event.sequence: reason='already_seen'
        elif event.action=='info_requested' and obj.status!='needs_info': reason='superseded'
        elif event.action in ('delivered','redelivered','delivery_rolled_back') and str(obj.current_delivery_id)!=event.details.get('delivery_id'): reason='superseded'
        elif event.action=='pending_reminder' and obj.status not in ('needs_info','delivered'): reason='superseded'
        elif obj.status in ('cancelled','rejected') and event.action not in ('cancelled','rejected'): reason='superseded'
        pref=NotificationPreference.objects.filter(user=obj.owner,topic_key='diary.customization',channel='apns').first()
        if not reason and pref and not pref.enabled: reason='topic_opt_out'
        suppression=NotificationCenterService._suppression_reason(user=obj.owner,channel='apns',topic_key='diary.customization')
        if not reason and suppression=='quiet_hours':
            # Bounded next check respects actual user timezone and expired/replaced events on every pass.
            box.status='pending';box.available_at=now+timedelta(minutes=5);box.last_error='deferred_quiet_hours';box.save()
            return
        if not reason and suppression: reason=suppression
        dev=DeviceSessionService.apns_trusted_device_for_user(user=obj.owner)
        if not reason and not dev: reason='no_push_enabled_device'
        if reason:
            box.status='processed';box.last_error=reason;box.save()
            intent.status='expired' if reason=='expired' else 'cancelled';intent.save(update_fields=['status','updated_at'])
            return
        recipient,_=NotificationRecipientMessage.objects.get_or_create(intent=intent,recipient_key=str(obj.owner_id),
            defaults={'user':obj.owner,'recipient_type':'user'})
        message=NotificationMessage.objects.filter(intent=intent,channel='apns').first()
        body,action=MESSAGES[event.action]
        title='专属定制'
        if intent.template_version_id:
            title=intent.template_version.title_template or title
            body=intent.template_version.body_template or body
        payload=dict(schema_version=1,scene_key=intent.business_scene,event_id=str(event.pk),event_sequence=event.sequence,
            request_id=str(obj.pk),delivery_id=event.details.get('delivery_id'),action=action,occurred_at=event.created_at.isoformat())
        if not message:
            message=NotificationMessage.objects.create(intent=intent,recipient_message=recipient,user=obj.owner,channel='apns',
                recipient_type='user',recipient_key=str(obj.owner_id),title=title,body=body,payload=payload,request_id=str(event.pk))
        delivery=ChannelDelivery.objects.filter(message=message).first()
        if not delivery: delivery=ChannelDelivery.objects.create(message=message,channel='apns',attempt_count=0)
        if delivery.status=='accepted':
            box.status='processed';box.save();return
        if delivery.next_retry_at and delivery.next_retry_at>now: return
        delivery.attempt_count+=1;delivery.next_retry_at=now+timedelta(seconds=90);delivery.status='processing';delivery.save()
        token=dev.push_token;topic=dev.bundle_identifier or dev.bundle_id
    ok,reason,apns_id=APNsProvider.send(device_token=token,title=title,body=body,payload=payload,topic=topic,
        expiration=int(intent.expires_at.timestamp()),collapse_id=f'custom-{obj.pk}',thread_id=f'custom-{obj.pk}',category='DIARY_CUSTOMIZATION')
    with transaction.atomic():
        box=NotificationOutbox.objects.select_for_update().get(pk=box.pk)
        delivery.refresh_from_db()
        result=_SendResult(accepted=ok,delivered=False,unknown=False,skipped=False,reason=reason,
            provider_message_id=apns_id,provider_request_id=f'{event.pk}:{delivery.attempt_count}',provider_status='accepted' if ok else 'failed')
        message.target_count=1;message.success_count=1 if ok else 0;message.failure_count=0 if ok else 1
        NotificationCenterService._record_message_event(message=message,channel='apns',provider='apns',result=result,existing_delivery=delivery)
        temporary=reason.startswith('request_error:') or reason in ('TooManyRequests','ServiceUnavailable','InternalServerError','Shutdown')
        if not ok and temporary and delivery.attempt_count<5:
            box.status='pending';box.available_at=timezone.now()+timedelta(seconds=min(900,15*2**delivery.attempt_count)*random.uniform(0.8,1.2));box.last_error='temporary_apns_failure'
            delivery.next_retry_at=box.available_at
        else:
            box.status='processed';box.last_error='' if ok else reason[:128]
            intent.status='completed' if ok else 'failed';intent.save(update_fields=['status','updated_at'])
            delivery.next_retry_at=None
        delivery.save(update_fields=['next_retry_at']);box.save()
        if reason=='Unregistered':
            type(dev).objects.filter(pk=dev.pk,push_token=token).update(push_token='',notifications_enabled=False)
