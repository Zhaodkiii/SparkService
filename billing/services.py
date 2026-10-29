import hashlib
import json
import uuid
from datetime import timedelta, datetime, timezone as datetime_timezone
from django.conf import settings
from django.db import transaction, connection
from django.utils import timezone
from .models import (WalletGate,WalletSnapshot,ContentOffer,ContentPolicyRevision,ContentOwnership,OwnershipSlot,RedemptionQuote,RedemptionOrder,WalletOperation,WalletLedgerEntry,ReconciliationCase,MembershipSnapshot)
from .identity import BillingError
from .flags import enabled
from .provider import RevenueCat,operation_body,diamond_balance

TERMINAL = ('fulfilled','rejected','compensated')
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def refresh_membership(identity,force=False):
    from .membership import refresh
    return refresh(identity, force=force)

def has_member(identity):
    refresh_membership(identity)
    from .membership import is_active
    return is_active(MembershipSnapshot.objects.filter(identity=identity).first(), identity)

def owns(identity,offer):
    return ContentOwnership.objects.filter(identity=identity,target_kind=offer.target_kind,target_id=offer.target_id,state='active').exists()

def target_available(offer):
    if offer.target_kind == "font":
        from font_library.models import FontFamily
        return FontFamily.objects.filter(pk=offer.target_id,active=True,current__isnull=False).exists()
    if offer.target_kind == 'template':
        from diary_presets.models import Template
        return Template.objects.filter(pk=offer.target_id,active=True,audience='public',series__active=True,current__isnull=False).exists()
    if offer.target_kind == 'sticker_library':
        from material_library.views import visible
        return visible().filter(pk=offer.target_id).exists()
    return False

def wallet(identity,refresh=False):
    snapshot,_=WalletSnapshot.objects.get_or_create(identity=identity)
    if refresh:
        refresh_membership(identity,force=True)
        version = snapshot.version
        result=RevenueCat().balance(identity)
        try:
            if result.status != 200: raise ValueError()
            balance=diamond_balance(result.body)
            # A late refresh must not overwrite a newer spend or refresh.
            WalletSnapshot.objects.filter(identity=identity,version=version).update(provider_balance=balance,fetched_at=timezone.now(),version=version+1,sync_state='fresh')
        except ValueError:
            WalletSnapshot.objects.filter(identity=identity,version=version).update(sync_state='stale')
        snapshot.refresh_from_db()
    gate=WalletGate.objects.get(identity=identity)
    return dict(currency='DIAMOND',balance=snapshot.provider_balance,version=snapshot.version,balance_state=snapshot.sync_state,wallet_domain=identity.wallet_domain,fetched_at=snapshot.fetched_at,can_redeem=enabled('DIAMOND_REDEMPTION_ENABLED',identity) and gate.state=='ready',pending_order_id=str(gate.active_operation.order_id) if gate.active_operation_id and gate.active_operation.order_id else None)

def quote(identity,offer):
    if owns(identity,offer): raise BillingError('ALREADY_OWNED','已经永久解锁此内容')
    policy=offer.current_policy_revision
    if offer.state!='active' or not policy or not target_available(offer): raise BillingError('CONTENT_UNAVAILABLE','内容暂不可兑换')
    if policy.access_mode not in ('diamond_only','pro_or_diamond'): raise BillingError('CONTENT_UNAVAILABLE','此内容无需钻石兑换')
    return RedemptionQuote.objects.create(identity=identity,offer=offer,policy_revision=policy,quoted_units=policy.diamond_price,expires_at=timezone.now()+timedelta(minutes=10))

@transaction.atomic
def prepare(identity,quote_id,offer_id,client_key):
    try: key=uuid.UUID(str(client_key))
    except (ValueError,TypeError): raise BillingError('INVALID_IDEMPOTENCY_KEY',status=400)
    request_hash=digest({'quote_id':str(quote_id),'offer_id':str(offer_id)})
    gate=WalletGate.objects.select_for_update().get(identity=identity)
    previous=RedemptionOrder.objects.filter(identity=identity,client_request_key=key).first()
    if previous:
        if previous.request_hash!=request_hash: raise BillingError('IDEMPOTENCY_CONFLICT')
        return previous
    try: q=RedemptionQuote.objects.select_related('offer__current_policy_revision','policy_revision').get(pk=quote_id,offer_id=offer_id,identity=identity)
    except RedemptionQuote.DoesNotExist: raise BillingError('QUOTE_NOT_FOUND',status=404)
    offer=q.offer
    if owns(identity,offer): raise BillingError('ALREADY_OWNED','已经永久解锁此内容')
    slot,_=OwnershipSlot.objects.get_or_create(identity=identity,offer=offer)
    if slot.active_order_id: return slot.active_order
    if gate.active_operation_id or gate.state!='ready': raise BillingError('REDEMPTION_IN_PROGRESS','已有交易正在确认，请稍后查看钱包')
    if not enabled('DIAMOND_REDEMPTION_ENABLED',identity): raise BillingError('SALES_DISABLED','兑换暂未开放')
    if q.expires_at<=timezone.now(): raise BillingError('QUOTE_EXPIRED','报价已过期，请重新确认')
    if offer.current_policy_revision_id!=q.policy_revision_id: raise BillingError('PRICE_CHANGED','价格已变化，请重新确认')
    if offer.state!='active' or not target_available(offer): raise BillingError('CONTENT_UNAVAILABLE')
    order=RedemptionOrder.objects.create(identity=identity,offer=offer,quote=q,client_request_key=key,request_hash=request_hash,amount=q.quoted_units)
    reference=f'redeem:{order.pk}:debit'
    operation=WalletOperation.objects.create(identity=identity,order=order,kind='debit',delta=-q.quoted_units,reference=reference,request_body_hash=digest({'adjustments':{'DIAMOND':-q.quoted_units},'reference':reference}))
    gate.active_operation=operation; gate.state='syncing'; gate.version+=1; gate.save()
    slot.active_order=order; slot.save()
    return order

def settle_gate(gate):
    # A refund/environment webhook can quarantine the wallet while HTTP is in flight.
    gate.active_operation=None
    if gate.state not in ('refund_review','quarantined'):
        gate.state='ready'
    gate.version+=1
    gate.save()

def mark_unknown(gate):
    if gate.state not in ('refund_review','quarantined'):
        gate.state='unknown_operation'
    gate.save()

def release(order,gate):
    OwnershipSlot.objects.filter(identity=order.identity,offer=order.offer,active_order=order).update(active_order=None)
    settle_gate(gate)

def review(operation,gate,reason):
    operation.state='manual_review'; operation.lease_until=None; operation.save()
    mark_unknown(gate)
    ReconciliationCase.objects.get_or_create(operation=operation,defaults=dict(identity=operation.identity,kind=reason,evidence={'order_id':str(operation.order_id)}))

def process(operation_id):
    """Operation row is the durable outbox; a periodic sweep recovers broker loss."""
    initial=WalletOperation.objects.get(pk=operation_id)
    if initial.funding_id:
        from .customization import process_funding
        return process_funding(operation_id)
    with transaction.atomic():
        gate=WalletGate.objects.select_for_update().get(identity=initial.identity)
        op=WalletOperation.objects.select_for_update().select_related('identity','order__quote__policy_revision','order__offer').get(pk=operation_id)
        if op.state in ('succeeded','rejected','manual_review') or gate.active_operation_id!=op.pk: return
        if op.lease_until and op.lease_until>timezone.now(): return
        if op.next_attempt_at and op.next_attempt_at>timezone.now(): return
        if op.identity.state!='active' or gate.state=='refund_review': return
        if digest(operation_body(op))!=op.request_body_hash: review(op,gate,'request_body_changed'); return
        if op.first_sent_at:
            window=settings.REVENUECAT_CONFIRMED_REPLAY_SECONDS
            if not window or timezone.now()-op.first_sent_at>timedelta(seconds=window):
                review(op,gate,'replay_window_unverified'); return
        elif op.kind=='debit':
            order=op.order; offer=ContentOffer.objects.get(pk=order.offer_id)
            if offer.current_policy_revision_id!=order.quote.policy_revision_id or offer.state!='active' or not target_available(offer):
                op.state='rejected';op.save();order.status='rejected';order.last_error_code='PRICE_CHANGED';order.save();release(order,gate);return
        token=uuid.uuid4(); op.lease_token=token;op.lease_until=timezone.now()+timedelta(seconds=60)
        op.first_sent_at=op.first_sent_at or timezone.now();op.attempt_count+=1;op.state='submitting';op.save()
        op.order.status='debiting' if op.kind=='debit' else 'compensating';op.order.save()
    result=RevenueCat().transact(op)
    with transaction.atomic():
        gate=WalletGate.objects.select_for_update().get(identity=op.identity)
        current=WalletOperation.objects.select_for_update().get(pk=op.pk)
        if current.lease_token!=token: return
        order=RedemptionOrder.objects.select_for_update().select_related('quote__policy_revision','offer').get(pk=op.order_id)
        current.response_status=result.status or None;current.response_body=result.body;current.lease_until=None
        try: balance=diamond_balance(result.body) if result.status==200 else None
        except ValueError: balance=None
        if result.status==200 and balance is not None:
            current.state='succeeded';current.save()
            snapshot=WalletSnapshot.objects.select_for_update().get(identity=op.identity)
            snapshot.provider_balance=balance;snapshot.version+=1;snapshot.fetched_at=timezone.now();snapshot.sync_state='fresh';snapshot.save()
            WalletLedgerEntry.objects.get_or_create(source_key=f'operation:{op.pk}',defaults=dict(identity=op.identity,delta=op.delta,observed_balance=balance,entry_kind=op.kind,title=order.offer.title,order=order))
            if op.kind=='debit':
                policy=order.quote.policy_revision
                # Frozen policy grants survive later price/publication changes.
                grants=[dict(target_kind=order.offer.target_kind,target_id=str(order.offer.target_id))]+policy.bundled_grants
                for grant in grants:
                    ContentOwnership.objects.get_or_create(source_order=order,grant_line=f"{grant['target_kind']}:{grant['target_id']}",defaults=dict(identity=op.identity,target_kind=grant['target_kind'],target_id=grant['target_id'],terms_snapshot={'terms_version':policy.terms_version,'scope':policy.content_scope_snapshot}))
                order.status='fulfilled';order.fulfilled_at=timezone.now()
            else: order.status='compensated'
            order.save()
            release(order,gate)
        elif result.status in (400,401,403,404,409,422):
            # Do not guess that any 422 is a declined payment. Preserve evidence for reconciliation.
            review(current,gate,'provider_rejected_or_conflicted')
            order.status='debit_unknown' if op.kind=='debit' else 'refund_unknown';order.last_error_code='PROVIDER_UNAVAILABLE';order.save()
        else:
            current.state='unknown';current.next_attempt_at=timezone.now()+timedelta(seconds=max(result.retry_after,min(900,2**min(current.attempt_count,9))));current.save()
            order.status='debit_unknown' if op.kind=='debit' else 'refund_unknown';order.save()
            mark_unknown(gate)
