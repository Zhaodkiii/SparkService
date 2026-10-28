"""Explicit audited compensation; never compensate an unknown debit."""
from django.db import transaction
from .models import WalletGate,WalletOperation,ContentOwnership,BillingAudit
from .identity import BillingError
from .services import digest

@transaction.atomic
def compensate(operation_id,actor,reason):
    if not reason or len(reason)>500: raise BillingError('REFUND_REASON_REQUIRED')
    debit=WalletOperation.objects.select_related('identity','order','funding').get(pk=operation_id,kind='debit')
    gate=WalletGate.objects.select_for_update().get(identity=debit.identity)
    debit=WalletOperation.objects.select_for_update().get(pk=debit.pk)
    if debit.state!='succeeded': raise BillingError('DEBIT_NOT_CONFIRMED')
    if debit.identity.state!='active' or gate.state=='refund_review': raise BillingError('WALLET_UNDER_REVIEW')
    lookup={'order_id':debit.order_id} if debit.order_id else {'funding_id':debit.funding_id}
    existing=WalletOperation.objects.filter(kind='compensation',**lookup).first()
    if existing:return existing
    if gate.active_operation_id: raise BillingError('REDEMPTION_IN_PROGRESS')
    amount=-debit.delta
    reference=f'compensate:{debit.pk}'
    op=WalletOperation.objects.create(identity=debit.identity,kind='compensation',delta=amount,reference=reference,request_body_hash=digest({'adjustments':{'DIAMOND':amount},'reference':reference}),**lookup)
    if debit.order_id:
        ContentOwnership.objects.filter(source_order=debit.order,state='active').update(state='revoked')
        debit.order.status='compensating';debit.order.save()
    else:
        if debit.funding.request.status in ('in_production','delivered','completed','revision_requested'): raise BillingError('MANUAL_AFTERSALES_REQUIRED','已开工订单需人工售后核定')
        debit.funding.status='refund_pending';debit.funding.save()
    gate.active_operation=op;gate.state='syncing';gate.save()
    BillingAudit.objects.create(actor=actor,action='compensate',target=str(debit.pk),detail={'reason':reason,'amount':amount,'operation_id':str(op.pk)})
    return op
