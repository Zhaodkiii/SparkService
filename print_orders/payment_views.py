import uuid
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from .models import Order, PaymentChannel, PaymentConfig, PaymentAttempt, PaymentRefund, PaymentAudit, PaymentProbe
from .domain import Conflict
from . import payment_config as vault, payments, payment_provider as provider, alipay, wechat


class FinancePermission(BasePermission):
    def has_permission(self,request,view):
        return request.user and request.user.is_active and (request.user.is_superuser or request.user.has_perm('print_orders.refund_order'))

class ConfigPermission(BasePermission):
    def has_permission(self,request,view):
        return request.user and request.user.is_active and (request.user.is_superuser or request.user.has_perm('print_orders.change_paymentchannel'))


def channel_data(c, request=None):
    versions=c.versions.order_by('-id');latest=versions.first()
    def version(v):
        if not v: return None
        probes=v.probes.order_by('-created_at')
        from .payment_probes import data
        return {'id':v.id,'environment':v.environment,'public':v.public,'checked_at':v.checked_at,
                'verified_note':v.verified_note,'actor':v.actor,'created_at':v.created_at,
                'materials':vault.statuses(v),'tests':[data(p) for p in probes[:10]],
                'active_test':data(active) if (active:=probes.exclude(state__in=['closed','refunded','expired','discarded']).first()) else None,
                'test_paid':probes.filter(state='refunded').exists(),'test_closed':probes.filter(state='closed',close_kind='gateway').exists(),'test_expired':probes.filter(state='closed',close_kind='expired_absent').exists()}
    origin=request.build_absolute_uri('/').rstrip('/') if request else ''
    return {'code':c.pk,'enabled':c.enabled,'position':c.position,'revision':c.revision,'current_id':c.current_id,
            'draft':version(latest),'versions':[version(v) for v in versions[:20]],
            'suggested_callback':origin+'/api/v1/print/'+c.pk+'-notify/',
            'pending_count':PaymentAttempt.objects.filter(config__channel=c,active_slot=1).count()}


class Methods(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        return Response([{'id':c.code,'title':c.get_code_display()} for c in PaymentChannel.objects.filter(enabled=True,current__environment='production').order_by('position','code')])


class Pay(APIView):
    permission_classes=[IsAuthenticated]
    def post(self,request,pk):
        get_object_or_404(Order,pk=pk,owner=request.user)
        return Response(payments.start(pk,request.user,request.data.get('channel'),request.data.get('key')))


class Notify(APIView):
    authentication_classes=[];permission_classes=[]
    def post(self,request,channel):
        try:
            if channel=='alipay':
                values=request.POST.dict()
                identifier=uuid.UUID(values['out_trade_no'])
                a=PaymentAttempt.objects.select_related('config','order').filter(pk=identifier,config__channel_id='alipay').first() or PaymentProbe.objects.select_related('config').get(pk=identifier,config__channel_id='alipay')
                data=alipay.notification(values,vault.config(a.config))
                if data.get('trade_status') in ('TRADE_SUCCESS','TRADE_FINISHED'):
                    notify_paid(a,provider.paid_alipay(a,data))
                elif data.get('trade_status')=='TRADE_CLOSED':
                    if isinstance(a,PaymentProbe): PaymentProbe.objects.filter(pk=a.pk).exclude(state__in=['succeeded','refunded']).update(state='closed')
                    else: payments.apply_result(a.pk,{'state':'closed'})
                return HttpResponse('success')
            # The encrypted notification doesn't expose the merchant order number.
            # Try immutable versions matching the platform key ID; no OSS or remote key fetch.
            for version in PaymentConfig.objects.filter(channel_id='wechat').order_by('-id'):
                if version.public.get('PUBLIC_KEY_ID')!=request.headers.get('Wechatpay-Serial'): continue
                try:
                    with provider.wx(vault.config(version)): data=wechat.notification(request.headers,request.body)
                    identifier=uuid.UUID(data['out_trade_no'])
                    a=PaymentAttempt.objects.select_related('config','order').filter(pk=identifier,config=version).first() or PaymentProbe.objects.select_related('config').get(pk=identifier,config=version)
                    if data.get('appid')!=version.public['APPID'] or data.get('mchid')!=version.public['MCHID']: continue
                    if data.get('trade_state')=='SUCCESS': notify_paid(a,provider.paid_wechat(a,data))
                    return HttpResponse(status=204)
                except (ValueError,KeyError,PaymentAttempt.DoesNotExist,PaymentProbe.DoesNotExist): continue
            raise ValueError()
        except (ValueError,KeyError,TypeError,PaymentAttempt.DoesNotExist,PaymentProbe.DoesNotExist):
            return HttpResponse('failure',status=400)


class Channels(APIView):
    permission_classes=[ConfigPermission]
    def get(self,request):
        for code in ('wechat','alipay'): PaymentChannel.objects.get_or_create(code=code)
        return Response([channel_data(c,request) for c in PaymentChannel.objects.order_by('position','code')])
    @transaction.atomic
    def post(self,request):
        d=request.data; code=d.get('code')
        if code not in ('wechat','alipay'): raise ValidationError('渠道无效')
        c=get_object_or_404(PaymentChannel.objects.select_for_update(),pk=code)
        if d.get('revision')!=c.revision: raise Conflict('配置已变化，请刷新')
        action=d.get('action'); actor=request.user.get_username()
        if action=='save':
            public=d.get('public',{}); private=d.get('secrets',{})
            if not isinstance(public,dict) or not set(public).issubset(vault.PUBLIC_FIELDS) or not all(isinstance(v,str) and len(v)<=2048 for v in public.values()): raise ValidationError('基础配置无效')
            if not isinstance(private,dict) or not set(private).issubset(vault.SECRET_FIELDS) or not all(isinstance(v,str) and len(v)<=20000 for v in private.values()): raise ValidationError('密钥配置无效')
            previous=c.versions.order_by('-id').first()
            if previous and previous.environment!=d.get('environment','production'): previous=None
            merged=vault.secrets(previous) if previous else {}
            merged.update({k:v.strip() for k,v in private.items() if v.strip()})
            environment=d.get('environment','production')
            if environment not in ('production','sandbox'): raise ValidationError('环境无效')
            public={k:v.strip() for k,v in public.items()}
            normalized=vault.validate(code,public,merged,environment)
            if previous and previous.public==public and vault.secrets(previous)==normalized:
                previous.checked_at=timezone.now();previous.save(update_fields=['checked_at'])
            else:
                PaymentConfig.objects.create(channel=c,environment=environment,public=public,encrypted=vault.encrypt(normalized),checked_at=timezone.now(),actor=actor)
        elif action in ('check','publish'):
            v=get_object_or_404(PaymentConfig,pk=d.get('version_id'),channel=c)
            vault.validate(code,v.public,vault.secrets(v),v.environment)
            if action=='check': v.checked_at=timezone.now();v.save(update_fields=['checked_at'])
            else:
                note=d.get('verified_note','')
                if not isinstance(note,str) or len(note)>1000: raise ValidationError('启用备注最多 1000 字')
                note=note.strip()
                if not v.checked_at: raise ValidationError('请先保存并检查配置')
                if d.get('confirm_enable') is not True: raise ValidationError('请在确认窗口核对收款信息后启用')
                if v.environment!='production': raise ValidationError('测试配置不能向正式用户开放')
                v.verified_note=note;v.save(update_fields=['verified_note']);c.current=v;c.enabled=True
        elif action=='disable': c.enabled=False
        elif action=='position':
            position=d.get('position')
            if not isinstance(position,int) or not 0<=position<=100: raise ValidationError('排序须为 0–100')
            c.position=position
        else: raise ValidationError('操作无效')
        c.revision+=1;c.save()
        details={'revision':c.revision}
        if action=='publish':
            details.update(version=v.pk,confirmed=True,payment_refund_tested=v.probes.filter(state='refunded').exists(),close_tested=v.probes.filter(state='closed',close_kind='gateway').exists())
        payments.audit('config_'+action,code,actor,**details)
        return Response(channel_data(c,request))


from .payment_admin import (transaction_data, refund_data, Transactions, Refunds, Audit, Overview, Access, LedgerExport)


def notify_paid(a, result):
    if isinstance(a,PaymentProbe):
        from .payment_probes import paid
        paid(a.pk,result)
    else: payments.apply_result(a.pk,result)


class Probes(APIView):
    permission_classes=[ConfigPermission,FinancePermission]
    def post(self,request):
        from datetime import timedelta
        from . import payment_probes as probe
        action=request.data.get('action')
        if action=='create':
            # Serialize creation per configuration. A lost HTTP response must not trap an active test.
            with transaction.atomic():
                v=get_object_or_404(PaymentConfig.objects.select_for_update(),pk=request.data.get('version_id'))
                vault.validate(v.channel_id,v.public,vault.secrets(v),v.environment)
                if not v.checked_at: raise ValidationError('请先保存并检查配置')
                if v.environment!='production': raise ValidationError('此入口用于正式 APP 联调；沙箱不支持发布')
                v.probes.filter(state='created',expires_at__lte=timezone.now()).update(state='expired',last_error='')
                p=v.probes.exclude(state__in=['closed','refunded','expired','discarded']).order_by('-created_at').first()
                if p:
                    if not probe.data(p)['can_resume']: raise Conflict('旧测试单已发起支付，请先查询并确认关单或退款，再创建新单')
                else:
                    p=PaymentProbe.objects.create(config=v,actor=request.user.get_username(),expires_at=timezone.now()+timedelta(minutes=10))
                    payments.audit('probe_create',p.pk,request.user.get_username(),version=v.pk)
            return Response(probe_link_data(p,request))
        p=get_object_or_404(PaymentProbe,pk=request.data.get('id'))
        if action=='link':
            if not probe.data(p)['can_resume']: raise Conflict('扫码链接已过期或测试已结束，请关闭后重新创建')
            return Response(probe_link_data(p,request))
        if action not in ('query','close'): raise ValidationError('操作无效')
        probe.sync(p.pk,close=action=='close');p.refresh_from_db()
        payments.audit('probe_'+action,p.pk,request.user.get_username())
        return Response(probe.data(p))


class ProbeLaunch(APIView):
    authentication_classes=[];permission_classes=[]
    def post(self,request,pk):
        from .payment_probes import launch
        p=get_object_or_404(PaymentProbe,pk=pk)
        import secrets
        if p.expires_at<=timezone.now() or not secrets.compare_digest(str(p.token),str(request.data.get('token',''))): raise ValidationError('联调链接无效或已过期')
        return Response(launch(p.pk))


def probe_link_data(p,request):
    from urllib.parse import urlencode
    from .payment_probes import data
    link='traveldiary-paytest://launch?'+urlencode({'id':str(p.pk),'token':str(p.token),'origin':request.build_absolute_uri('/').rstrip('/')})
    return {**data(p),'link':link}
