"""Operator read models, independently permissioned from pricing and refunds."""
from datetime import timedelta
from django.conf import settings
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from common.permissions import AdminCodePermission
from .views import AuthView
from .models import (BillingIdentity, StorePayment, TopUpRecord, RedemptionOrder, CustomizationFunding,
    WalletSnapshot, MembershipSnapshot, ContentOwnership, CurrencyEvent, ReconciliationCase, BillingAudit, ContentOffer)

class Filters(serializers.Serializer):
    environment=serializers.ChoiceField(choices=['sandbox','production'],default='production')
    section=serializers.ChoiceField(choices=['recharge','subscription','redemption','users','alerts','activity','customization'],default='recharge')
    page=serializers.IntegerField(min_value=1,max_value=100000,default=1)
    page_size=serializers.IntegerField(min_value=1,max_value=100,default=20)
    search=serializers.CharField(max_length=200,required=False,allow_blank=True)
    status=serializers.ChoiceField(choices=['all','confirmed','refunded','pending_delivery','unknown_amount','open'],default='all')
    identity=serializers.UUIDField(required=False)
    account=serializers.IntegerField(min_value=1,required=False)
    start=serializers.DateTimeField(required=False)
    end=serializers.DateTimeField(required=False)
    def validate(self,data):
        if data.get('start') and data.get('end') and data['start']>=data['end']:
            raise serializers.ValidationError('结束时间必须晚于开始时间')
        return data

def user_json(i):
    return dict(identity_id=str(i.pk),account_id=i.account_id,name=i.account.get_full_name() or i.account.username,
        environment=i.wallet_domain,rc_app_user_id=str(i.rc_app_user_id),state=i.state,
        revenuecat_url=f'https://app.revenuecat.com/projects/{i.rc_project_id}/customers/{i.rc_app_user_id}')

def payment_json(row, topups):
    topup=topups.get((row.identity_id,row.store_transaction_id))
    return dict(id=str(row.pk),**user_json(row.identity),product=row.product_id,kind=row.kind,
        amount=str(row.amount) if row.amount is not None else None,currency=row.currency,
        payment_state='refunded' if row.refund_state=='refunded' else 'confirmed' if row.payment_confirmed else 'unconfirmed',
        delivery_state=topup.state if topup else 'unconfirmed',expected_units=topup.expected_units if topup else None,
        verified_units=topup.verified_units if topup else None,lifecycle=('REFUND_CONFIRMED' if row.refund_state=='refunded' else 'RENEWAL_CANCELLED') if row.lifecycle=='CANCELLATION' else row.lifecycle,
        purchased_at=row.purchased_at,created_at=row.created_at,transaction_id=row.store_transaction_id)

class Transactions(AuthView):
    permission_classes=[AdminCodePermission]
    required_permission_code='billing.view_transactions'
    def get(self,request):
        f=Filters(data=request.query_params);f.is_valid(raise_exception=True);v=f.validated_data
        identities=BillingIdentity.objects.filter(rc_project_id=settings.REVENUECAT_PROJECT_ID,wallet_domain=v['environment'])
        if v.get('identity'): identities=identities.filter(pk=v['identity'])
        if v.get('account'): identities=identities.filter(account_id=v['account'])
        search=v.get('search','')
        if search:
            match=Q(account__username__icontains=search)|Q(account__first_name__icontains=search)|Q(account__last_name__icontains=search)
            if search.isdigit() and len(search)<=18: match |= Q(account_id=int(search))
            identities=identities.filter(match|Q(rc_app_user_id__icontains=search))
        section=v['section']
        if section in ('recharge','subscription'):
            qs=StorePayment.objects.filter(identity__in=identities,kind=section).select_related('identity__account')
        elif section=='redemption':
            qs=RedemptionOrder.objects.filter(identity__in=identities).select_related('identity__account','offer').prefetch_related('operations')
        elif section=='customization':
            qs=CustomizationFunding.objects.filter(identity__in=identities).select_related('identity__account','quote__package_revision__package').prefetch_related('operations')
        elif section=='activity': qs=CurrencyEvent.objects.filter(identity__in=identities).select_related('identity__account')
        elif section=='users': qs=identities.select_related('account','walletsnapshot','membershipsnapshot')
        else: qs=ReconciliationCase.objects.filter(Q(identity__in=identities)).select_related('identity__account')
        if section in ('recharge','subscription'):
            status=v['status']
            if status=='confirmed': qs=qs.filter(payment_confirmed=True).exclude(refund_state='refunded')
            elif status=='refunded': qs=qs.filter(refund_state='refunded')
            elif status=='unknown_amount': qs=qs.filter(amount__isnull=True)
            elif status=='pending_delivery':
                # TopUpRecord uses SHA256(store transaction ID); the payment digest includes its domain.
                from django.db.models import Exists,OuterRef
                pending=TopUpRecord.objects.filter(identity_id=OuterRef('identity_id'),store_transaction_id=OuterRef('store_transaction_id'),state__in=['grant_pending','purchase_observed','unknown'])
                any_topup=TopUpRecord.objects.filter(identity_id=OuterRef('identity_id'),store_transaction_id=OuterRef('store_transaction_id'))
                qs=qs.annotate(pending_topup=Exists(pending),has_topup=Exists(any_topup)).filter(Q(pending_topup=True)|Q(has_topup=False))
        elif section=='alerts' and v['status']=='open': qs=qs.filter(status='open')
        time_field='received_at' if section=='activity' else 'created_at'
        for key,lookup in [('start',time_field+'__gte'),('end',time_field+'__lt')]:
            if key in v: qs=qs.filter(**{lookup:v[key]})
        count=qs.count();offset=(v['page']-1)*v['page_size'];rows=list(qs.order_by('-'+time_field,'-pk')[offset:offset+v['page_size']])
        summary={}
        if section in ('recharge','subscription'):
            topups={(t.identity_id,t.store_transaction_id):t for t in TopUpRecord.objects.filter(identity_id__in=[r.identity_id for r in rows],store_transaction_id__in=[r.store_transaction_id for r in rows])}
            items=[payment_json(r,topups) for r in rows]
            summary={'amounts':list(qs.filter(payment_confirmed=True,refund_state__in=['none','reversed'],amount__isnull=False).values('currency').annotate(amount=Sum('amount'))),'unknown_amounts':qs.filter(amount__isnull=True).count()}
        elif section=='redemption':
            items=[dict(id=str(r.pk),**user_json(r.identity),title=r.offer.title,units=r.amount,status=r.status,created_at=r.created_at,error=r.last_error_code,
                operations=[dict(id=str(o.pk),kind=o.kind,state=o.state,delta=o.delta) for o in r.operations.all()]) for r in rows]
        elif section=='customization':
            items=[dict(id=str(r.pk),**user_json(r.identity),title=r.quote.package_revision.package.title,request_id=str(r.request_id),units=r.amount,status=r.status,created_at=r.created_at,
                operations=[dict(id=str(o.pk),kind=o.kind,state=o.state,delta=o.delta) for o in r.operations.all()]) for r in rows]
        elif section=='activity':
            items=[dict(id=str(r.pk),**user_json(r.identity),kind=r.payload.get('type'),status=r.state,created_at=r.received_at) for r in rows]
        elif section=='users':
            items=[]
            for r in rows:
                w=getattr(r,'walletsnapshot',None);m=getattr(r,'membershipsnapshot',None)
                items.append(dict(id=str(r.pk),**user_json(r),balance=w.provider_balance if w else None,balance_state=w.sync_state if w else 'unknown',fetched_at=w.fetched_at if w else None,member_until=m.active_until if m else None,member_verified_at=m.verified_at if m else None))
        else:
            items=[dict(id=str(r.pk),**user_json(r.identity),kind=r.kind,status=r.status,operation_id=r.operation_id,created_at=r.created_at) for r in rows]
        # Unlinked/quarantined callbacks are visible even when they have no resolved user.
        unlinked=CurrencyEvent.objects.filter(state='quarantined',identity__isnull=True,payload__app_id=settings.REVENUECAT_APP_ID).filter(Q(payload__environment=v['environment'].upper())|Q(payload__purchase_environment=v['environment']))
        overdue=TopUpRecord.objects.filter(identity__in=identities,state__in=['grant_pending','purchase_observed'],created_at__lt=timezone.now()-timedelta(minutes=5)).count()
        return Response(dict(pending_topups=overdue,items=items,total=count,page=v['page'],summary=summary,unlinked_events=unlinked.count(),environment=v['environment']))

class PaymentDetail(AuthView):
    permission_classes=[AdminCodePermission]
    required_permission_code='billing.view_transactions'
    def get(self,request,pk):
        row=get_object_or_404(StorePayment.objects.select_related('identity__account'),pk=pk,identity__rc_project_id=settings.REVENUECAT_PROJECT_ID)
        topup=TopUpRecord.objects.filter(identity=row.identity,store_transaction_id=row.store_transaction_id).first()
        result=payment_json(row,{(row.identity_id,row.store_transaction_id):topup} if topup else {})
        result['events']=[dict(event_id=e.event_id,type=e.payload.get('type'),state=e.state,received_at=e.received_at,cancel_reason=e.payload.get('cancel_reason')) for e in row.events.order_by('received_at','pk')[:100]]
        return Response(result)

class UserAssets(AuthView):
    permission_classes=[AdminCodePermission]
    @property
    def required_permission_code(self):
        return 'billing.sync_transactions' if self.request.method=='POST' else 'billing.view_transactions'
    def get(self,request,pk):
        identity=get_object_or_404(BillingIdentity.objects.select_related('account'),pk=pk,rc_project_id=settings.REVENUECAT_PROJECT_ID)
        w=WalletSnapshot.objects.filter(identity=identity).first();m=MembershipSnapshot.objects.filter(identity=identity).first()
        owned=list(ContentOwnership.objects.filter(identity=identity).order_by('-created_at')[:100])
        titles={(o.target_kind,o.target_id):o.title for o in ContentOffer.objects.filter(target_id__in=[o.target_id for o in owned])}
        return Response(dict(**user_json(identity),balance=w.provider_balance if w else None,balance_state=w.sync_state if w else 'unknown',fetched_at=w.fetched_at if w else None,member_until=m.active_until if m else None,member_verified_at=m.verified_at if m else None,
            ownership_count=ContentOwnership.objects.filter(identity=identity,state='active').count(),
            ownerships=[dict(target_kind=o.target_kind,target_id=o.target_id,title=titles.get((o.target_kind,o.target_id),'内容已下架或未命名'),state=o.state,created_at=o.created_at) for o in owned]))
    def post(self,request,pk):
        identity=get_object_or_404(BillingIdentity,pk=pk,rc_project_id=settings.REVENUECAT_PROJECT_ID)
        from .services import wallet
        result=wallet(identity,refresh=True)
        BillingAudit.objects.create(actor=request.user,action='sync_wallet_snapshot',target=str(pk),detail={'state':result['balance_state']})
        return Response(result)
