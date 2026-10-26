"""Operator-oriented payment records, explicit read/write actions and reconciliation totals."""
import csv
import io
import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.views import APIView
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied
from .models import PaymentAttempt, PaymentRefund, PaymentAudit
from . import payments


def allowed(user, permission):
    return bool(user and user.is_authenticated and user.is_active and (user.is_superuser or user.has_perm('print_orders.'+permission)))


def access(user):
    return {'view':any(allowed(user,p) for p in ('view_paymentattempt','query_payment','refund_order')),
            'query':allowed(user,'query_payment'),'refund':allowed(user,'refund_order'),
            'configure':allowed(user,'change_paymentchannel'),'orders':allowed(user,'change_order')}


class ReadPermission(BasePermission):
    def has_permission(self,request,view): return access(request.user)['view']


class Access(APIView):
    def get(self,request): return Response(access(request.user))


def refund_data(r):
    return {'id':str(r.pk),'attempt_id':str(r.attempt_id),'order_id':str(r.attempt.order_id),
            'title':r.attempt.order.title,'channel':r.attempt.config.channel_id,'config_version':r.attempt.config_id,
            'order_state':r.attempt.order.state,'payment_state':r.attempt.state,'provider_id':r.provider_id,
            'payment_provider_id':r.attempt.provider_id,'amount':r.amount,'reason':r.reason,'state':r.state,
            'last_error':r.last_error,'error_code':r.error_code,'error_category':r.error_category,'recovery_action':r.recovery_action,
            'retry_mode':r.retry_mode,'failure_count':r.failure_count,'next_check_at':r.next_check_at,
            'created_at':r.created_at,'checked_at':r.checked_at,'completed_at':r.completed_at}


def transaction_data(a):
    try: r=a.refund
    except PaymentRefund.DoesNotExist: r=None
    return {'id':str(a.pk),'order_id':str(a.order_id),'title':a.order.title,'channel':a.config.channel_id,
            'config_version':a.config_id,'amount':a.amount,'state':a.state,'provider_id':a.provider_id,
            'order_state':a.order.state,'order_payment_state':a.order.payment_state,'refund':refund_data(r) if r else None,
            'failure_count':a.failure_count,'next_check_at':a.next_check_at if a.active_slot else None,'auto_paused':bool(a.active_slot and a.failure_count>=10),
            'created_at':a.created_at,'paid_at':a.paid_at,'checked_at':a.checked_at,'expires_at':a.expires_at,'last_error':a.last_error}


def filtered(qs,params,kind):
    if params.get('channel'):
        if params['channel'] not in ('wechat','alipay'): raise ValidationError('渠道无效')
        qs=qs.filter(**{('config__channel_id' if kind=='transactions' else 'attempt__config__channel_id'):params['channel']})
    if params.get('id'):
        try: qs=qs.filter(pk=uuid.UUID(params['id']))
        except (ValueError,TypeError): raise ValidationError('记录单号无效')
    if params.get('state'):
        value=params['state']
        if kind=='refunds' and value=='open': qs=qs.filter(state__in=['pending','processing','unknown'])
        elif kind=='refunds' and value=='blocked_all': qs=qs.filter(state__in=['blocked','exception'])
        else: qs=qs.filter(state=value)
    term=params.get('q','').strip()
    if term:
        if kind=='transactions': p=Q(provider_id__icontains=term)|Q(order__title__icontains=term)
        else: p=Q(provider_id__icontains=term)|Q(attempt__provider_id__icontains=term)|Q(attempt__order__title__icontains=term)
        try:
            identifier=uuid.UUID(term)
            p|=Q(id=identifier)|Q(**{('order_id' if kind=='transactions' else 'attempt__order_id'):identifier})
            if kind=='refunds': p|=Q(attempt_id=identifier)
        except (ValueError,TypeError): pass
        qs=qs.filter(p)
    for key,op in [('date_from','gte'),('date_to','lt')]:
        if params.get(key):
            try: day=parse_date(params[key])
            except (ValueError,TypeError): day=None
            if not day: raise ValidationError('日期格式应为 YYYY-MM-DD')
            if key=='date_to': day+=timedelta(days=1)
            qs=qs.filter(**{'created_at__'+op:datetime.combine(day,time.min,tzinfo=ZoneInfo('Asia/Shanghai'))})
    if kind=='refunds':
        if params.get('error_category'): qs=qs.filter(error_category=params['error_category'])
        if params.get('queue')=='paused': qs=qs.exclude(state='success').filter(retry_mode='paused')
        if params.get('queue')=='processing': qs=qs.filter(state__in=['pending','processing','unknown'])
        if params.get('queue')=='blocked': qs=qs.filter(state__in=['blocked','exception'])
    elif params.get('queue')=='uncertain': qs=qs.filter(Q(state='unknown')|Q(failure_count__gte=10))
    return qs


def paginate(qs,request,serializer):
    try: page=max(1,int(request.query_params.get('page',1)))
    except (ValueError,TypeError): raise ValidationError('页码无效')
    return {'count':qs.count(),'results':[serializer(r) for r in qs[(page-1)*30:page*30]]}


def operation_audit(action, row, actor, call):
    before=row.state
    try:
        value=call();row.refresh_from_db()
        payments.audit(action,row.pk,actor,result='success',before=before,after=row.state,source='manual')
        return value
    except Exception as exc:
        row.refresh_from_db()
        payments.audit(action,row.pk,actor,result='failed',before=before,after=row.state,source='manual',error_code=getattr(exc,'gateway_code',type(exc).__name__))
        raise


class Transactions(APIView):
    permission_classes=[ReadPermission]
    def get(self,request):
        qs=filtered(PaymentAttempt.objects.select_related('config','order','refund__attempt__config','refund__attempt__order').order_by('-created_at','-id'),request.query_params,'transactions')
        return Response(paginate(qs,request,transaction_data))
    def post(self,request):
        if not access(request.user)['query']: raise PermissionDenied('没有查询渠道及关单权限')
        a=get_object_or_404(PaymentAttempt.objects.select_related('config','order'),pk=request.data.get('id'))
        action=request.data.get('action')
        if action not in ('query','close'): raise ValidationError('操作无效')
        if action=='close' and request.data.get('confirmed') is not True: raise ValidationError('请先核对订单后确认关单')
        operation_audit('transaction_'+action,a,request.user.get_username(),lambda:payments.sync(a.pk,close=action=='close'))
        a=PaymentAttempt.objects.select_related('config','order').get(pk=a.pk)
        return Response(transaction_data(a))


class Refunds(APIView):
    permission_classes=[ReadPermission]
    def get(self,request):
        qs=filtered(PaymentRefund.objects.select_related('attempt__config','attempt__order').order_by('-created_at','-id'),request.query_params,'refunds')
        return Response(paginate(qs,request,refund_data))
    def post(self,request):
        action=request.data.get('action')
        if action not in ('query','retry','resume','pause'): raise ValidationError('请选择查询、重试、恢复自动处理或暂停')
        capability='query' if action=='query' else 'refund'
        if not access(request.user)[capability]: raise PermissionDenied('没有执行此退款操作的权限')
        if action in ('retry','resume') and request.data.get('confirmed') is not True: raise ValidationError('请核对订单、退款金额及原因后确认')
        r=get_object_or_404(PaymentRefund,pk=request.data.get('id'))
        payments.sync_refund(r.pk,action=action,actor=request.user.get_username())
        r=PaymentRefund.objects.select_related('attempt__config','attempt__order').get(pk=r.pk)
        return Response(refund_data(r))


class Audit(APIView):
    permission_classes=[ReadPermission]
    def get(self,request):
        qs=PaymentAudit.objects.order_by('-id')
        term=request.query_params.get('q','').strip()
        if term:
            references=Q(reference__icontains=term)
            try:
                identifier=uuid.UUID(term)
                refs=[str(identifier)]
                refs.extend(str(x) for x in PaymentAttempt.objects.filter(order_id=identifier).values_list('pk',flat=True))
                refs.extend(str(x) for x in PaymentRefund.objects.filter(Q(attempt__order_id=identifier)|Q(attempt_id=identifier)).values_list('pk',flat=True))
                references|=Q(reference__in=refs)
            except ValueError: pass
            qs=qs.filter(references)
        for param,field in [('actor','actor__icontains'),('action','action')]:
            if request.query_params.get(param): qs=qs.filter(**{field:request.query_params[param]})
        if request.query_params.get('id'):
            try: qs=qs.filter(pk=int(request.query_params['id']))
            except (ValueError,TypeError): raise ValidationError('记录单号无效')
        if request.query_params.get('result'): qs=qs.filter(details__result=request.query_params['result'])
        return Response(paginate(qs,request,lambda r:{'id':r.pk,'actor':r.actor or '系统','action':r.action,'reference':r.reference,'details':r.details,'created_at':r.created_at}))


class Overview(APIView):
    permission_classes=[ReadPermission]
    def get(self,request):
        a=PaymentAttempt.objects.all();r=PaymentRefund.objects.all()
        total=lambda q: q.aggregate(n=Sum('amount'))['n'] or 0
        # Payment/refund records are an internal ledger, not a provider settlement balance.
        return Response({'uncertain':a.filter(Q(state='unknown')|Q(failure_count__gte=10)).count(),
                         'processing':r.filter(state__in=['pending','processing','unknown']).count(),
                         'blocked':r.filter(state__in=['blocked','exception']).count(),
                         'paused':r.exclude(state='success').filter(retry_mode='paused').count(),
                         'paid_fen':total(a.filter(state='succeeded')),'refunded_fen':total(r.filter(state='success')),
                         'outstanding_refund_fen':total(r.exclude(state='success')),
                         'order_due_fen':sum_row_orders(a),'settlement_available':False})


def sum_row_orders(attempts):
    from .models import Order
    return Order.objects.filter(pk__in=attempts.values('order_id')).aggregate(n=Sum('total_fen'))['n'] or 0


class LedgerExport(APIView):
    permission_classes=[ReadPermission]
    def get(self,request):
        kind=request.query_params.get('kind')
        if kind not in ('transactions','refunds'): raise ValidationError('导出类型无效')
        qs=PaymentAttempt.objects.select_related('order','config') if kind=='transactions' else PaymentRefund.objects.select_related('attempt__order','attempt__config')
        qs=filtered(qs,request.query_params,kind).order_by('-created_at')
        if qs.count()>10000: raise ValidationError('最多导出 10000 条，请缩小日期范围')
        output=io.StringIO();writer=csv.writer(output)
        writer.writerow(['记录类型','单号','订单号','渠道','金额（元）','状态','创建时间（北京时间）'])
        for row in qs:
            data=(transaction_data if kind=='transactions' else refund_data)(row)
            writer.writerow([kind,data['id'],data['order_id'],data['channel'],f"{data['amount']/100:.2f}",data['state'],row.created_at.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')])
        payments.audit('ledger_export',kind,request.user.get_username(),result='success',count=qs.count(),source='manual')
        return Response({'filename':kind+'.csv','csv':'\ufeff'+output.getvalue()})
