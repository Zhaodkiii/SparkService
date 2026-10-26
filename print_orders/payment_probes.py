"""Isolated administrator APP payment checks, with automatic full refunds."""
from datetime import timedelta
from types import SimpleNamespace
from django.db import transaction
from django.utils import timezone
from .models import PaymentProbe
from .domain import Conflict
from . import payment_provider as gateway


def data(p):
    return {'id':str(p.pk),'state':p.state,'refund_state':p.refund_state,'amount':p.amount,
            'created_at':p.created_at,'expires_at':p.expires_at,'actor':p.actor,
            'can_resume':p.state in ('created','pending','unknown') and p.expires_at>timezone.now(),
            'close_kind':p.close_kind,'expired':p.expires_at<=timezone.now(),'last_error':'' if p.state=='created' else p.last_error}


def acquire(pk):
    with transaction.atomic():
        p=PaymentProbe.objects.select_for_update().select_related('config').get(pk=pk)
        if p.lease_until and p.lease_until>timezone.now(): raise Conflict('测试单正在处理，请稍后刷新')
        p.lease_until=timezone.now()+timedelta(seconds=90);p.save(update_fields=['lease_until'])
        return p


def paid(pk,result):
    with transaction.atomic():
        p=PaymentProbe.objects.select_for_update().get(pk=pk)
        if p.provider_id and p.provider_id!=result['provider_id']: raise Conflict('测试流水不一致')
        p.provider_id=result['provider_id']
        if p.state!='refunded': p.state='succeeded'
        p.save(update_fields=['provider_id','state'])


def launch(pk):
    p=acquire(pk)
    try:
        if p.expires_at<=timezone.now() or p.state not in ('created','pending','unknown'): raise Conflict('测试单已结束，请重新创建')
        # Query any prior launch before returning the same immutable payment intent.
        if p.state!='created':
            result=gateway.query(p)
            if result['state']=='succeeded': paid(p.pk,result);raise Conflict('测试已付款，正在等待退款')
            if result['state'] in ('closed','failed'): raise Conflict('测试交易已结束')
        payload,prepay=gateway.create(p)
        PaymentProbe.objects.filter(pk=pk).exclude(state__in=['succeeded','refunded']).update(state='pending',prepay_id=prepay,last_error='')
        return {'attempt_id':str(p.pk),'channel':p.config.channel_id,'expires_at':p.expires_at,'parameters':payload}
    except Exception:
        PaymentProbe.objects.filter(pk=pk,state='created').update(state='unknown')
        raise
    finally: PaymentProbe.objects.filter(pk=pk).update(lease_until=None)


def sync(pk,close=False):
    p=acquire(pk)
    try:
        if p.state in ('closed','refunded','expired','discarded'): return
        if p.state=='created':
            # No SDK signature has ever been issued. There is nothing to query or close remotely.
            state='discarded' if close else 'expired' if p.expires_at<=timezone.now() else 'created'
            PaymentProbe.objects.filter(pk=pk).update(state=state,last_error='')
            return
        result=gateway.query(p)
        if result['state']=='succeeded':
            paid(p.pk,result);p.refresh_from_db()
            # Same refund id is reused on every retry, including timeouts.
            r=SimpleNamespace(attempt=p,id=p.refund_id,amount=p.amount,reason='管理员联调完成自动退款',state=p.refund_state)
            refunded=gateway.query_refund(r) if r.state=='processing' else gateway.refund(r)
            if refunded['state']=='absent': refunded={'state':'processing'}
            PaymentProbe.objects.filter(pk=pk).update(refund_state=refunded['state'],state='refunded' if refunded['state']=='success' else 'succeeded',last_error='')
        elif result['state'] in ('closed','failed'):
            PaymentProbe.objects.filter(pk=pk).update(state='closed',close_kind='gateway',last_error='')
        elif close or p.expires_at<=timezone.now():
            if result['state']=='absent':
                if p.expires_at>timezone.now(): raise Conflict('APP 签名尚未到期，请在支付 App 取消后等待过期关单')
                PaymentProbe.objects.filter(pk=pk).update(state='closed',close_kind='expired_absent',last_error='')
            else:
                gateway.close(p)
                result=gateway.query(p)
                if result['state']=='succeeded': paid(p.pk,result)
                elif result['state'] in ('closed','absent'): PaymentProbe.objects.filter(pk=pk).update(state='closed',close_kind='gateway',last_error='')
                else: raise Conflict('关单尚未确认，请稍后刷新')
    except Conflict as exc:
        PaymentProbe.objects.filter(pk=pk).update(last_error=str(exc.detail))
        raise
    except Exception as exc:
        from .payment_errors import GatewayError
        PaymentProbe.objects.filter(pk=pk).update(last_error=(str(exc.detail)+'；'+exc.action)[:200] if isinstance(exc,GatewayError) else '测试结果尚未确认，请查询或稍后重试')
        raise
    finally: PaymentProbe.objects.filter(pk=pk).update(lease_until=None)
