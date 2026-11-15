"""Server authoritative invitation qualification and idempotent award issuance."""
from datetime import timedelta
import hashlib
import hmac
from urllib.parse import urlparse
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError, PermissionDenied
from accounts.models import SocialIdentity
from .models import *


def normalize(kind, contact):
    from rest_framework import serializers
    if kind == 'email':
        return serializers.EmailField().run_validation(contact).strip().lower()
    if kind == 'phone':
        from accounts.services.phone_number_service import PhoneNumberService
        return PhoneNumberService.normalize_e164(contact)
    raise ValidationError('请选择手机号或邮箱')


def contact_digest(kind, value):
    return hmac.new(settings.SECRET_KEY.encode(), ('invitation:'+kind+':'+value).encode(), hashlib.sha256).hexdigest()


def validate_campaign(c):
    u=urlparse(c.download_url)
    if u.scheme!='https' or u.hostname!='apps.apple.com' or '/id' not in u.path:
        raise ValidationError('请配置真实的苹果 App Store 产品地址')
    if c.ends_at<=c.starts_at or not 1<=c.attribution_days<=30 or not 1<=c.card_days<=365:
        raise ValidationError('活动期限或卡有效期不正确')
    if c.cards_per_invite>10 or c.card_invite_limit>100 or not c.participant_limit or not c.rules.strip():
        raise ValidationError('请完整配置奖励规则和名额')
    from print_orders.models import PrintCampaign
    p=PrintCampaign.objects.select_for_update().get(pk=c.print_campaign_id)
    if not p.product_id or not p.product.active or not p.product.proof_approved or p.product.free_printing:
        raise ValidationError('请选择可售且已通过打样的标准印制产品')
    if c.participant_limit>p.quota: raise ValidationError('参与名额超过关联印制活动预留名额')
    if InvitationCampaign.objects.filter(print_campaign=p).exclude(pk=c.pk).exists(): raise ValidationError('该印制活动已关联其他邀请活动，请使用独立名额')
    if p.source != 'invitation': raise ValidationError('请选择邀请来源的实体书活动')
    if p.cap_fen < p.product.base_fen+p.product.page_fen*p.included_pages:
        raise ValidationError('免费装订抵扣上限必须覆盖承诺的标准规格')
    if not c.print_snapshot:
        c.print_snapshot=dict(product_id=str(p.product_id),included_pages=p.included_pages,cap_fen=p.cap_fen,valid_days=p.valid_days)
        c.save(update_fields=['print_snapshot'])


def available(c):
    now=timezone.now()
    return c.active and c.starts_at<=now<c.ends_at


@transaction.atomic
def join(user,campaign):
    get_user_model().objects.select_for_update().get(pk=user.pk)
    if not user.social_identities.exclude(provider='device').exists():
        raise PermissionDenied('请先登录或绑定正式账号')
    c=InvitationCampaign.objects.select_for_update().get(pk=campaign.pk)
    if not available(c): raise ValidationError('活动暂不可参加')
    existing=InvitationLink.objects.filter(owner=user,campaign=c).first()
    if existing: return existing
    if InvitationLink.objects.filter(campaign=c).count()>=c.participant_limit:
        raise ValidationError('活动名额已满')
    return InvitationLink.objects.create(owner=user,campaign=c)


@transaction.atomic
def register(link,kind,value):
    if not available(link.campaign) or not link.owner.is_active: raise ValidationError('邀请活动已结束')
    value=normalize(kind,value)
    if SocialIdentity.objects.filter(provider=kind,provider_uid=value).exists():
        raise ValidationError('该联系方式不符合新用户邀请条件')
    # Registration is a candidate, not ownership. Never locks a contact to an inviter.
    return InvitationRegistration.objects.get_or_create(link=link,contact_kind=kind,contact_hash=contact_digest(kind,value),
        defaults={'expires_at':min(link.campaign.ends_at,timezone.now()+timedelta(days=link.campaign.attribution_days))})[0]


@transaction.atomic
def process_identity(event_id):
    event=InvitationIdentityEvent.objects.select_for_update().select_related('identity__user').get(pk=event_id)
    if event.processed_at: return
    identity=event.identity; user=identity.user
    get_user_model().objects.select_for_update().get(pk=user.pk)
    now=timezone.now()
    event.attempts+=1
    if identity.provider in ('phone','email') and user.is_active and not InvitationConversion.objects.filter(invitee=user).exists():
        digest=contact_digest(identity.provider,normalize(identity.provider,identity.provider_uid))
        candidates=InvitationRegistration.objects.filter(contact_kind=identity.provider,contact_hash=digest,
            expires_at__gt=now,created_at__lte=identity.created_at,link__campaign__active=True,
            link__campaign__ends_at__gt=now).exclude(link__owner=user).select_related('link__campaign')
        # Without Web OTP, conflicting inviters cannot be safely auto-attributed.
        if candidates.values('link__owner_id').distinct().count()==1:
            reg=candidates.order_by('created_at').first()
            if reg and not user.social_identities.exclude(provider='device').filter(created_at__lt=reg.created_at).exists():
                link=InvitationLink.objects.select_for_update().get(pk=reg.link_id)
                InvitationConversion.objects.create(registration=reg,invitee=user)
                count=InvitationConversion.objects.filter(registration__link=link).count()
                c=link.campaign
                if c.cards_per_invite and count<=c.card_invite_limit:
                    InvitationReward.objects.get_or_create(key=f'invite:{link.pk}:card:{count}',defaults=dict(link=link,kind='reset_card',threshold=count,quantity=c.cards_per_invite))
                for threshold,kind in [(5,'half_print'),(10,'free_print')]:
                    if count>=threshold:
                        InvitationReward.objects.get_or_create(key=f'invite:{link.pk}:print:{threshold}',defaults=dict(link=link,kind=kind,threshold=threshold))
    event.processed_at=now; event.save(update_fields=['processed_at','attempts'])


@transaction.atomic
def issue(reward_id,actor=None,reason='自动发放'):
    r=InvitationReward.objects.select_for_update().select_related('link__campaign__print_campaign__product').get(pk=reward_id)
    if r.issued_at: return r
    c=r.link.campaign
    if InvitationConversion.objects.filter(registration__link=r.link).count()<r.threshold:
        raise ValidationError('尚未达标')
    from ai_production.models import ProductionResetCard
    from print_orders.models import PrintCoupon
    from print_orders.campaigns import reward_name
    now=timezone.now()
    if r.kind=='reset_card':
        for n in range(r.quantity):
            ProductionResetCard.objects.get_or_create(grant_key=f'{r.key}:{n}',defaults=dict(owner=r.link.owner,expires_at=now+timedelta(days=c.card_days)))
    else:
        p=c.print_campaign; percent=50 if r.kind=='half_print' else 100
        snapshot=c.print_snapshot or dict(product_id=p.product_id,included_pages=p.included_pages,cap_fen=p.cap_fen,valid_days=p.valid_days)
        r.coupon,_=PrintCoupon.objects.get_or_create(grant_key=r.key,defaults=dict(owner=r.link.owner,product_id=snapshot['product_id'],name='邀请奖励 · 标准装订半价券' if percent==50 else '邀请奖励 · 标准装订免费券',percent=percent,included_pages=snapshot['included_pages'],cap_fen=snapshot['cap_fen'],expires_at=now+timedelta(days=snapshot['valid_days'])))
    r.issued_at=now; r.save(update_fields=['issued_at','coupon'])
    InvitationAudit.objects.create(actor=actor,action='reward.issued',target=r.key,reason=reason)
    return r
