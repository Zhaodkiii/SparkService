from .models import ContentOffer,ContentOwnership
from .identity import identity_for,BillingError
from .services import has_member

def describe(request,kind,target_id):
    offer=ContentOffer.objects.select_related('current_policy_revision').filter(target_kind=kind,target_id=target_id).first()
    # Existing free content is explicitly seeded by migration 0002. New content fails closed.
    if not offer and kind=='template':
        from diary_presets.models import Template
        if Template.objects.filter(pk=target_id,audience='private',owner=request.user,versions__custom_delivery__status='delivered').exists():
            return dict(commerce=None,access=dict(can_use=True,reason='private_delivery',permanently_owned=True,can_redeem=False,can_preview=True))
    if not offer:
        return dict(commerce=None,access=dict(can_use=False,reason='policy_pending',permanently_owned=False,can_redeem=False,can_preview=True))
    policy=offer.current_policy_revision
    owned=False; member=False
    if request.headers.get('X-Billing-Session'):
        identity=identity_for(request)
        owned=ContentOwnership.objects.filter(identity=identity,target_kind=kind,target_id=target_id,state='active').exists()
        member=has_member(identity)
    mode=policy.access_mode if policy else None
    can_use=owned or mode=='free' or (member and mode in ('pro_only','pro_or_diamond'))
    return dict(commerce=dict(offer_id=str(offer.pk),policy_revision=policy.revision if policy else 0,access_mode=mode,diamond_price=policy.diamond_price if policy else None,currency='DIAMOND' if policy and policy.diamond_price else None),access=dict(can_use=can_use,reason='owned' if owned else 'free' if mode=='free' else 'pro' if can_use else 'locked',permanently_owned=owned,can_redeem=not owned and offer.state=='active' and mode in ('diamond_only','pro_or_diamond'),can_preview=True))

def require_content(request,kind,target_id):
    data=describe(request,kind,target_id)
    if not data['access']['can_use']: raise BillingError('CONTENT_LOCKED','请先开通对应会员权益或永久解锁内容',403)
    return data
