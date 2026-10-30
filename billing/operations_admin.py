"""Operator-facing wallet investigation; never initiates a wallet transaction on GET."""
import uuid
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from common.permissions import AdminCodePermission
from .views import AuthView
from .models import WalletOperation, ContentOwnership, ContentOffer, ReconciliationCase


def operations():
    return WalletOperation.objects.select_related('identity__account', 'identity__walletgate', 'order__offer', 'funding__request')


def operation_json(op, detail=False):
    linked = {'order_id':op.order_id} if op.order_id else {'funding_id':op.funding_id}
    compensation = WalletOperation.objects.filter(kind='compensation', **linked).first() if op.kind=='debit' else None
    gate = getattr(op.identity, 'walletgate', None)
    reason = ''
    if op.kind != 'debit' or op.state != 'succeeded': reason='仅确认成功的扣钻可以申请补偿'
    elif compensation: reason='此笔扣钻已提交补偿，请查看补偿处理状态'
    elif not gate or gate.state=='refund_review' or op.identity.state!='active': reason='钱包需人工核查'
    elif gate.active_operation_id: reason='钱包仍有交易处理中，请等待完成'
    elif op.funding_id and op.funding.request.status in ('in_production','delivered','completed','revision_requested'): reason='制作已开始，请进入专属定制人工售后'
    result=dict(id=str(op.pk),identity_id=str(op.identity_id),account_id=op.identity.account_id,
                name=op.identity.account.get_username(),environment=op.identity.wallet_domain,
                title=op.order.offer.title if op.order_id else op.funding.request.title,
                order_id=str(op.order_id) if op.order_id else None, funding_id=str(op.funding_id) if op.funding_id else None,
                request_id=str(op.funding.request_id) if op.funding_id else None,
                kind=op.kind,delta=op.delta,state=op.state,attempt_count=op.attempt_count,created_at=op.created_at,
                can_compensate=not reason,compensation_reason=reason,
                compensation=dict(id=str(compensation.pk),state=compensation.state,amount=compensation.delta) if compensation else None)
    if detail:
        grants=ContentOwnership.objects.filter(source_order_id=op.order_id,state='active') if op.order_id else ContentOwnership.objects.none()
        titles={(o.target_kind,o.target_id):o.title for o in ContentOffer.objects.filter(target_id__in=grants.values('target_id'))}
        result['revoked_grants']=[dict(title=titles.get((g.target_kind,g.target_id),str(g.target_id)),target_kind=g.target_kind,target_id=str(g.target_id)) for g in grants]
        result['cases']=list(ReconciliationCase.objects.filter(operation=op).values('kind','status','created_at'))
    return result


class OperationQuery(serializers.Serializer):
    q=serializers.CharField(required=False,allow_blank=True,max_length=160,default='')
    environment=serializers.ChoiceField(choices=['production','sandbox'],default='production')
    state=serializers.ChoiceField(choices=['','prepared','submitting','succeeded','unknown','manual_review','rejected'],default='')
    page=serializers.IntegerField(min_value=1,default=1)
    page_size=serializers.IntegerField(min_value=1,max_value=100,default=20)


def list_operations(params):
    form=OperationQuery(data=params);form.is_valid(raise_exception=True);d=form.validated_data
    qs=operations().filter(identity__wallet_domain=d['environment'])
    if d['state']: qs=qs.filter(state=d['state'])
    if d['q']:
        search=Q(identity__account__username__icontains=d['q'])|Q(order__offer__title__icontains=d['q'])|Q(funding__request__title__icontains=d['q'])
        try:
            key=uuid.UUID(d['q']);search|=Q(pk=key)|Q(order_id=key)|Q(funding_id=key)
        except ValueError: pass
        qs=qs.filter(search)
    total=qs.count();start=(d['page']-1)*d['page_size']
    return dict(items=[operation_json(o) for o in qs.order_by('-created_at','id')[start:start+d['page_size']]], total=total, page=d['page'])


class ManageOperationDetail(AuthView):
    permission_classes=[AdminCodePermission]
    required_permission_code='billing.view_transactions'
    def get(self,request,pk):
        return Response(operation_json(get_object_or_404(operations(),pk=pk),detail=True))
