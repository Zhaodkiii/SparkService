from celery import shared_task
from .models import InvitationIdentityEvent, InvitationReward
from .invitations import process_identity, issue
import logging
logger=logging.getLogger(__name__)
@shared_task
def process_invitation_rewards():
    for pk in InvitationIdentityEvent.objects.filter(processed_at__isnull=True).order_by('pk').values_list('pk',flat=True)[:100]:
        try: process_identity(pk)
        except Exception: logger.exception('Invitation identity event failed: %s',pk)
    for pk in InvitationReward.objects.filter(issued_at__isnull=True,link__campaign__automatic=True).values_list('pk',flat=True)[:100]:
        try: issue(pk)
        except Exception: logger.exception('Invitation reward failed: %s',pk)

    for reward in InvitationReward.objects.filter(issued_at__isnull=False,notified_at__isnull=True).select_related('link')[:100]:
        try:
            from notification_center.services import NotificationCenterService
            from django.utils import timezone
            NotificationCenterService.send_to_user_sync(campaign_id=None,user_id=reward.link.owner_id,channels=['in_app'],title='邀请奖励已到账',body='你的邀请奖励已发放，请前往邀请有礼查看重置卡或印制优惠券。',payload={'route':'invitations','reward_id':reward.pk},created_by_id=None,business_scene='growth.invitation.reward_issued',business_reference_type='invitation_reward',business_id=str(reward.pk),idempotency_key='invitation-reward:'+str(reward.pk),source='public_experience')
            InvitationReward.objects.filter(pk=reward.pk).update(notified_at=timezone.now())
        except Exception: logger.exception('Invitation reward notification failed: %s',reward.pk)
