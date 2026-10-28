from datetime import datetime, timezone as dt_timezone
from celery import shared_task
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import CurrencyEvent,BillingIdentity,WalletGate,WalletLedgerEntry,WalletSnapshot,ReconciliationCase,MembershipSnapshot,WalletOperation
from .services import process

@shared_task
def process_pending():
    ids=list(WalletOperation.objects.filter(state__in=['prepared','unknown','submitting']).filter(Q(next_attempt_at__isnull=True)|Q(next_attempt_at__lte=timezone.now())).values_list('pk',flat=True)[:100])
    for pk in ids: process(pk)
    for pk in CurrencyEvent.objects.filter(state='pending').values_list('pk',flat=True)[:100]: process_event(pk)
    from datetime import timedelta
    from .membership import refresh
    due=MembershipSnapshot.objects.filter(Q(needs_sync=True)|Q(active_until__isnull=False, verified_at__lt=timezone.now()-timedelta(minutes=15))).select_related('identity')
    for row in due.order_by('verified_at')[:100]: refresh(row.identity,force=True)

@transaction.atomic
def process_event(pk):
    event=CurrencyEvent.objects.select_for_update().get(pk=pk)
    if event.state!='pending': return
    data=event.payload
    if data.get('type') == 'TRANSFER':
        # Never merge wallet identities or business ownerships on a store transfer.
        import uuid
        ids=[]
        for raw in (data.get('transferred_from') or []) + (data.get('transferred_to') or []):
            try: ids.append(uuid.UUID(str(raw)))
            except (TypeError,ValueError): pass
        for identity in BillingIdentity.objects.filter(rc_app_user_id__in=ids):
            member,_=MembershipSnapshot.objects.select_for_update().get_or_create(identity=identity)
            member.needs_sync=True;member.last_event_at=timezone.now();member.verified_at=None
            member.save(update_fields=['needs_sync','last_event_at','verified_at'])
        event.state='processed';event.save();return
    try: identity=BillingIdentity.objects.get(rc_app_user_id=data.get('app_user_id'))
    except (BillingIdentity.DoesNotExist,ValueError,TypeError,DjangoValidationError):
        event.state='quarantined';event.save();return
    gate,_=WalletGate.objects.get_or_create(identity=identity)
    gate=WalletGate.objects.select_for_update().get(pk=gate.pk)
    event.identity=identity
    raw_environment=data.get('purchase_environment',data.get('environment',''))
    environment=raw_environment.lower() if isinstance(raw_environment,str) else ''
    if environment not in ('sandbox','production'):
        event.state='quarantined';event.save()
        ReconciliationCase.objects.get_or_create(identity=identity,kind='event_environment_unverified',evidence={'event_id':event.event_id})
        return
    if environment!=identity.wallet_domain:
        identity.state='quarantined';identity.save();gate.state='quarantined';gate.save()
        event.state='quarantined';event.save()
        ReconciliationCase.objects.create(identity=identity,kind='environment_mismatch',evidence={'event_id':event.event_id});return
    from .topups import observe
    if data.get('type') in ('NON_RENEWING_PURCHASE','CANCELLATION'):
        if observe(identity,data) is False:
            event.state='quarantined';event.save();return
    if data.get('type')=='VIRTUAL_CURRENCY_TRANSACTION':
        adjustments=data.get('adjustments')
        if not isinstance(adjustments,list) or any(not isinstance(a,dict) or not isinstance(a.get('currency'),dict) or type(a.get('amount'))!=int for a in adjustments):
            event.state='quarantined';event.save();return
        if sum(a['currency'].get('code')=='DIAMOND' for a in adjustments)>1:
            event.state='quarantined';event.save();return
        for adjustment in adjustments:
            if adjustment['currency'].get('code')!='DIAMOND': continue
            amount=adjustment.get('amount')
            if type(amount)!=int: event.state='quarantined';event.save();return
            origin=data.get('source')
            if origin=='in_app_purchase':
                topup=observe(identity,data,amount)
                if topup is False or topup is None:
                    event.state='quarantined';event.save();gate.state='unknown_operation';gate.save();return
            elif origin!='admin_api':
                event.state='quarantined';event.save();return
            source=str(data.get('virtual_currency_transaction_id') or event.event_id)
            WalletLedgerEntry.objects.get_or_create(source_key='rc:DIAMOND:'+source,defaults=dict(identity=identity,delta=amount,entry_kind=('recharge' if amount>0 else 'refund') if origin=='in_app_purchase' else 'adjustment',title=('钻石充值' if amount>0 else '充值退款回收') if origin=='in_app_purchase' else '钻石调整'))
            if amount<0:
                gate.state='refund_review';gate.save()
                ReconciliationCase.objects.get_or_create(identity=identity,kind='refund_exposure',evidence={'event_id':event.event_id})
        WalletSnapshot.objects.filter(identity=identity).update(sync_state='stale')
    if 'member' in (data.get('entitlement_ids') or []) or data.get('type') in ('CANCELLATION','INITIAL_PURCHASE','RENEWAL','EXPIRATION','BILLING_ISSUE','PRODUCT_CHANGE','UNCANCELLATION','SUBSCRIPTION_EXTENDED','REFUND_REVERSED'):
        # Events invalidate; re-read current provider state, never grant from an old event.
        member,_=MembershipSnapshot.objects.select_for_update().get_or_create(identity=identity)
        member.needs_sync=True
        member.last_event_at=timezone.now()
        if data.get('type') == 'EXPIRATION' or (data.get('type') == 'CANCELLATION' and data.get('cancel_reason') == 'CUSTOMER_SUPPORT'):
            member.verified_at=None
        member.save(update_fields=['needs_sync','last_event_at','verified_at'])
    event.state='processed';event.save()
    from .reporting import project
    project(event)
