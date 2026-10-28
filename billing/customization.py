"""Digital commissioning funding; never uses content ownership locks."""
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from .models import CustomizationPackageRevision,CustomizationQuote,CustomizationFunding,WalletGate,WalletOperation,WalletSnapshot,WalletLedgerEntry,BillingAudit,ReconciliationCase
from .identity import BillingError
from .flags import enabled
from .services import digest,has_member,review,settle_gate,mark_unknown
from .provider import RevenueCat,operation_body,diamond_balance
from diary_customizations.models import Request

@transaction.atomic
def issue_quote(request_id,package_revision_id,actor):
    request=Request.objects.select_for_update().get(pk=request_id,deleted_at__isnull=True)
    if request.status not in ('submitted','needs_info'):
        raise BillingError('CUSTOMIZATION_STATE_INVALID','只有未开始制作的需求可报价')
    if CustomizationFunding.objects.filter(request=request).exclude(status__in=['rejected','price_changed']).exists(): raise BillingError('FUNDING_EXISTS')
    package=CustomizationPackageRevision.objects.select_related('package').get(pk=package_revision_id)
    if package.package.state!='active': raise BillingError('PACKAGE_UNAVAILABLE')
    if package.max_photos>30 or request.assets.filter(deleted_at__isnull=True).count()>package.max_photos:
        raise BillingError('PACKAGE_CAPACITY_EXCEEDED')
    submission=request.submissions.order_by('-number').first()
    if not submission: raise BillingError('SCOPE_NOT_ACCEPTED','请先提交需求范围')
    number=(CustomizationQuote.objects.filter(request=request).aggregate(value=Max('revision'))['value'] or 0)+1
    quote=CustomizationQuote.objects.create(request=request,package_revision=package,revision=number,expected_request_revision=request.revision,standard_diamonds=package.standard_diamonds,pro_diamonds=package.pro_diamonds,scope_snapshot={'submission_id':str(submission.pk),'title':request.title,'included_pages':package.included_pages,'max_photos':package.max_photos,'revision_rounds':package.included_revision_rounds,'lead_workdays':package.lead_workdays,'terms_version':package.terms_version},expires_at=timezone.now()+timedelta(hours=72),actor=actor)
    BillingAudit.objects.create(actor=actor,action='customization_quote',target=str(request.pk),detail={'quote_id':str(quote.pk),'revision':number})
    return quote

@transaction.atomic
def prepare_funding(identity,request_id,quote_id,quote_revision,expected_revision,key,expected_total):
    key=uuid.UUID(str(key))
    gate=WalletGate.objects.select_for_update().get(identity=identity)
    request=Request.objects.select_for_update().get(pk=request_id,owner=identity.account,deleted_at__isnull=True)
    hash_=digest({'request_id':str(request_id),'quote_id':str(quote_id),'quote_revision':quote_revision,'expected_revision':expected_revision,'expected_total':expected_total})
    replay=CustomizationFunding.objects.filter(identity=identity,client_request_key=key).first()
    if replay:
        if replay.request_hash!=hash_: raise BillingError('IDEMPOTENCY_CONFLICT')
        return replay
    previous=CustomizationFunding.objects.filter(request=request).exclude(status__in=['price_changed','rejected']).first()
    if previous:
        if previous.identity_id!=identity.pk: raise BillingError('WALLET_DOMAIN_CONFLICT')
        if previous.client_request_key==key and previous.request_hash!=hash_: raise BillingError('IDEMPOTENCY_CONFLICT')
        return previous
    if not enabled('DIAMOND_CUSTOMIZATION_ENABLED',identity): raise BillingError('SALES_DISABLED','数字定制支付尚未开放')
    if gate.state!='ready' or gate.active_operation_id: raise BillingError('REDEMPTION_IN_PROGRESS')
    q=CustomizationQuote.objects.select_related('package_revision').get(pk=quote_id,request=request,revision=quote_revision)
    if q.expires_at<=timezone.now(): raise BillingError('QUOTE_EXPIRED')
    if q.expected_request_revision!=expected_revision or request.revision!=expected_revision: raise BillingError('PRICE_CHANGED')
    if request.status not in ('submitted','needs_info'): raise BillingError('CUSTOMIZATION_STATE_INVALID')
    use_pro=has_member(identity) and q.pro_diamonds is not None
    amount=q.pro_diamonds if use_pro else q.standard_diamonds
    if amount!=expected_total: raise BillingError('PRICE_CHANGED','会员资格或报价已变化，请重新确认金额')
    funding=CustomizationFunding.objects.create(request=request,identity=identity,quote=q,client_request_key=key,request_hash=hash_,amount=amount,used_pro_price=use_pro)
    reference=f'custom:{funding.pk}:debit'
    op=WalletOperation.objects.create(identity=identity,funding=funding,kind='debit',delta=-amount,reference=reference,request_body_hash=digest({'adjustments':{'DIAMOND':-amount},'reference':reference}))
    gate.active_operation=op;gate.state='syncing';gate.version+=1;gate.save()
    return funding

def process_funding(operation_id):
    initial=WalletOperation.objects.get(pk=operation_id)
    with transaction.atomic():
        gate=WalletGate.objects.select_for_update().get(identity=initial.identity)
        op=WalletOperation.objects.select_for_update().select_related('identity','funding__quote','funding__request').get(pk=operation_id)
        if op.state in ('succeeded','rejected','manual_review') or gate.active_operation_id!=op.pk: return
        if op.identity.state!='active' or gate.state=='refund_review': return
        if op.lease_until and op.lease_until>timezone.now(): return
        if op.next_attempt_at and op.next_attempt_at>timezone.now(): return
        if digest(operation_body(op))!=op.request_body_hash: review(op,gate,'request_body_changed');return
        if op.first_sent_at:
            window=settings.REVENUECAT_CONFIRMED_REPLAY_SECONDS
            if not window or timezone.now()-op.first_sent_at>timedelta(seconds=window): review(op,gate,'replay_window_unverified');return
        elif op.kind=='debit' and (op.funding.request.status not in ('submitted','needs_info') or op.funding.request.revision!=op.funding.quote.expected_request_revision or (op.funding.used_pro_price and not has_member(op.identity))):
            op.state='rejected';op.save();op.funding.status='price_changed';op.funding.save();settle_gate(gate);return
        op.lease_token=uuid.uuid4();token=op.lease_token;op.lease_until=timezone.now()+timedelta(seconds=60)
        op.first_sent_at=op.first_sent_at or timezone.now();op.attempt_count+=1;op.state='submitting';op.save()
        op.funding.status='processing';op.funding.save()
    result=RevenueCat().transact(op)
    with transaction.atomic():
        gate=WalletGate.objects.select_for_update().get(identity=op.identity)
        current=WalletOperation.objects.select_for_update().get(pk=op.pk)
        if current.lease_token!=token:return
        funding=CustomizationFunding.objects.select_for_update().get(pk=op.funding_id)
        current.response_status=result.status or None;current.response_body=result.body;current.lease_until=None
        try: balance=diamond_balance(result.body) if result.status==200 else None
        except ValueError: balance=None
        if balance is not None:
            current.state='succeeded';current.save();funding.status='funded' if op.kind=='debit' else 'refunded';funding.save()
            snapshot=WalletSnapshot.objects.select_for_update().get(identity=op.identity);snapshot.provider_balance=balance;snapshot.version+=1;snapshot.fetched_at=timezone.now();snapshot.sync_state='fresh';snapshot.save()
            WalletLedgerEntry.objects.get_or_create(source_key=f'operation:{op.pk}',defaults=dict(identity=op.identity,delta=op.delta,observed_balance=balance,entry_kind='customization',title=funding.quote.scope_snapshot.get('title','数字定制')))
            settle_gate(gate)
        else:
            funding.status='unknown';funding.save()
            if result.status in (400,401,403,404,409,422): review(current,gate,'provider_rejected_or_conflicted')
            else:
                current.state='unknown';current.next_attempt_at=timezone.now()+timedelta(seconds=result.retry_after);current.save();mark_unknown(gate)
