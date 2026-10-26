"""Durable payment intents. All gateway calls happen outside database transactions."""
import uuid
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import Order, PaymentAttempt, PaymentChannel, PaymentRefund, PaymentAudit
from .domain import Conflict, Unavailable
from . import payment_provider as gateway


def audit(action, reference, actor='', **details):
    PaymentAudit.objects.create(action=action,reference=str(reference),actor=actor,details=details)


def locked_attempt(pk):
    # Always lock order first, including callbacks, to avoid cross-channel deadlocks.
    order_id=PaymentAttempt.objects.only('order_id').get(pk=pk).order_id
    order=Order.objects.select_for_update().get(pk=order_id)
    return order, PaymentAttempt.objects.select_for_update().select_related('config','order').get(pk=pk)


def apply_result(pk, result):
    from .services import event
    with transaction.atomic():
        o,a=locked_attempt(pk)
        a.checked_at=timezone.now(); a.last_error=''; a.failure_count=0; a.next_check_at=timezone.now()+timedelta(seconds=30)
        if result['state']=='succeeded':
            identifier=result['provider_id']
            if a.provider_id and a.provider_id!=identifier: raise Conflict('支付流水不一致')
            a.state='succeeded'; a.provider_id=identifier; a.active_slot=None
            if not a.paid_at: a.paid_at=timezone.now()
            a.save()
            # Order transaction id is a summary; prefix prevents cross-provider collisions.
            summary=a.config.channel_id+':'+identifier
            if o.transaction_id and o.transaction_id!=summary:
                PaymentRefund.objects.get_or_create(attempt=a,defaults={'amount':a.amount,'reason':'重复付款自动原路退回'})
                audit('duplicate_payment',a.pk)
            elif not o.transaction_id:
                o.transaction_id=summary
                if o.cancel_requested or o.state=='cancelled':
                    o.payment_state='refund_pending';o.refund_state='pending';o.refund_reason='取消订单后收到付款'
                    PaymentRefund.objects.get_or_create(attempt=a,defaults={'amount':a.amount,'reason':o.refund_reason})
                else:
                    o.payment_state='paid'
                    if o.file_state=='ready': o.state='awaiting_review'
                event(o,'paid',('微信支付' if a.config.channel_id=='wechat' else '支付宝')+'已确认')
                audit('paid',a.pk)
        elif a.state!='succeeded':
            a.state='pending' if result['state']=='absent' else result['state']
            if a.state in ('closed','failed'): a.active_slot=None
            a.save()
    return PaymentAttempt.objects.select_related('config','order').get(pk=pk)


def acquire(pk):
    with transaction.atomic():
        _,a=locked_attempt(pk)
        if a.lease_until and a.lease_until>timezone.now(): raise Conflict('支付结果正在确认，请稍后刷新')
        a.lease_until=timezone.now()+timedelta(seconds=90);a.save(update_fields=['lease_until'])
        return a


def release(pk): PaymentAttempt.objects.filter(pk=pk).update(lease_until=None,checked_at=timezone.now())


def sync(pk, close=False):
    a=acquire(pk)
    try:
        result=gateway.query(a)
        a=apply_result(pk,result)
        if close and a.state not in ('succeeded','closed','failed'):
            # For APP signatures, an absent trade can still be paid until expiry.
            if result['state']=='absent':
                if a.expires_at>timezone.now(): raise Conflict('原支付单尚未结束，请使用原渠道或等待支付期限结束')
            else:
                gateway.close(a)
                result=gateway.query(a)
                if result['state']=='succeeded': return apply_result(pk,result)
                if result['state'] not in ('closed','absent'): raise Unavailable('关单结果尚未确认')
            a=apply_result(pk,{'state':'closed'})
        return a
    except Conflict as exc:
        PaymentAttempt.objects.filter(pk=pk).exclude(state__in=['succeeded','closed','failed']).update(last_error=str(exc.detail))
        raise
    except Exception as exc:
        current=PaymentAttempt.objects.get(pk=pk)
        failures=current.failure_count+1
        PaymentAttempt.objects.filter(pk=pk).exclude(state__in=['succeeded','closed','failed']).update(state='unknown',last_error='渠道处理结果待确认' if failures<10 else '多次查询失败，请人工处理',failure_count=failures,next_check_at=timezone.now()+timedelta(seconds=min(30*2**min(failures,5),900)),checked_at=timezone.now())
        raise
    finally: release(pk)


def start(order_id, owner, channel, key):
    from .payment_config import config
    if channel not in ('wechat','alipay'): raise Conflict('请选择有效的支付方式')
    try: key=uuid.UUID(str(key))
    except (ValueError,TypeError): raise Conflict('支付请求标识无效')
    current=PaymentAttempt.objects.filter(order_id=order_id,active_slot=1).first()
    if current and current.config.channel_id!=channel:
        sync(current.pk,close=True)
    with transaction.atomic():
        o=Order.objects.select_for_update().get(pk=order_id,owner=owner)
        if o.total_fen<=0 or o.payment_state!='unpaid' or o.state!='draft' or o.file_state!='ready' or o.cancel_requested: raise Conflict('当前订单不可支付，请刷新')
        if not o.product.active: raise Conflict('该规格已暂停接单')
        if o.payment_expires_at and o.payment_expires_at<=timezone.now(): raise Conflict('支付期限已过，请取消订单后重新下单')
        c=PaymentChannel.objects.select_related('current').filter(pk=channel,enabled=True,current__isnull=False).first()
        if not c: raise Unavailable('该支付方式暂不可用')
        if c.current.environment!='production': raise Unavailable('测试配置不能用于正式印制订单')
        config(c.current)  # Check local decryption before recording an intent.
        prior=PaymentAttempt.objects.filter(order=o,key=key).first()
        if prior and (prior.config.channel_id!=channel or prior.active_slot is None): raise Conflict('该支付请求已结束，请刷新后重试')
        a=PaymentAttempt.objects.filter(order=o,active_slot=1).first()
        if a and a.config.channel_id!=channel: raise Conflict('其他支付交易尚未关闭')
        if not o.payment_expires_at: o.payment_expires_at=timezone.now()+timedelta(minutes=30)
        o.payment_started=True;o.save()
        if not a: a=PaymentAttempt.objects.create(order=o,config=c.current,key=key,amount=o.total_fen,expires_at=o.payment_expires_at)
    a=acquire(a.pk)
    try:
        if a.state!='creating' or a.last_error:
            result=gateway.query(a)
            if result['state']=='succeeded':
                apply_result(a.pk,result);raise Conflict('订单已付款，请刷新订单')
            if result['state'] in ('closed','failed'):
                apply_result(a.pk,result);raise Conflict('原交易已结束，请重试')
        payload,prepay=gateway.create(a)
        with transaction.atomic():
            o,current=locked_attempt(a.pk)
            if current.state=='succeeded' or o.cancel_requested: raise Conflict('订单已变化，请刷新')
            current.state='pending';current.prepay_id=prepay;current.last_error='';current.save()
        return {'attempt_id':str(a.pk),'channel':channel,'expires_at':a.expires_at,'parameters':payload}
    except Exception:
        PaymentAttempt.objects.filter(pk=a.pk,state='creating').update(state='unknown',last_error='支付请求结果待确认')
        raise
    finally: release(a.pk)


def _save_refund_result(pk, result):
    from .services import event
    with transaction.atomic():
        r=PaymentRefund.objects.select_related('attempt__config').get(pk=pk)
        o=Order.objects.select_for_update().get(pk=r.attempt.order_id)
        current=PaymentRefund.objects.select_for_update().get(pk=pk)
        if current.state=='success': return
        old=current.state
        state=result['state']
        if state=='absent':
            # A read-only query cannot silently retry a rejected refund or clear its cause.
            current.checked_at=timezone.now();current.save(update_fields=['checked_at']);return
        current.state=state;current.provider_id=result.get('provider_id','')
        current.last_error='';current.error_code='';current.error_category='';current.recovery_action=''
        current.failure_count=0;current.next_check_at=None if current.retry_mode=='paused' else timezone.now()+timedelta(seconds=60)
        if state=='success': current.completed_at=timezone.now();current.next_check_at=None
        if state=='exception': current.retry_mode='paused';current.recovery_action='请核对渠道退款记录并人工处理'
        current.save()
        if o.transaction_id==r.attempt.config.channel_id+':'+str(r.attempt.provider_id):
            o.refund_state=state;o.payment_state='refunded' if state=='success' else 'refund_pending'
            if old!=state: event(o,'refund_'+state,'退款'+{'success':'已完成','processing':'处理中','exception':'需要处理'}.get(state,'待处理'))
            else: o.save()


def sync_refund(pk, action='auto', actor=''):
    from .payment_errors import GatewayError
    if action not in ('auto','query','retry','resume','pause'): raise Conflict('退款操作无效')
    with transaction.atomic():
        r=PaymentRefund.objects.select_for_update().select_related('attempt__config','attempt__order').get(pk=pk)
        if r.lease_until and r.lease_until>timezone.now(): raise Conflict('退款正在核对，请稍后刷新')
        if r.state=='success': return
        if action=='auto' and r.retry_mode=='paused': return
        if action=='pause':
            r.retry_mode='paused';r.next_check_at=None;r.save(update_fields=['retry_mode','next_check_at'])
            audit('refund_pause',pk,actor,result='success',before=r.state,after=r.state,source='manual');return
        if action=='resume': r.retry_mode='auto';r.failure_count=0
        r.lease_until=timezone.now()+timedelta(seconds=90);r.save()
    before=r.state
    source='automatic' if action=='auto' else 'manual'
    try:
        # Queries never submit. Uncertain/previous submissions are always checked before retry.
        result=None
        if action=='query' or r.submission_started or r.state=='processing':
            result=gateway.query_refund(r)
        if action!='query' and (result is None or result['state']=='absent'):
            PaymentRefund.objects.filter(pk=pk).update(submission_started=True)
            result=gateway.refund(r)
            if result['state']=='absent': result={'state':'processing','provider_id':''}
        _save_refund_result(pk,result)
        current=PaymentRefund.objects.get(pk=pk)
        audit('refund_'+action,pk,actor,result='success',before=before,after=current.state,channel_state=result['state'],source=source)
    except Conflict:
        raise
    except Exception as exc:
        current=PaymentRefund.objects.get(pk=pk);failures=current.failure_count+1
        known=isinstance(exc,GatewayError)
        category=exc.category if known else 'unknown'
        blocked=known and category=='balance'
        paused=(known and category!='balance') or (not known and failures>=10)
        state='blocked' if blocked else 'exception' if known else 'unknown'
        message=str(exc.detail) if known else '渠道退款结果暂未确认，请先查询渠道结果'
        recovery=exc.action if known else '查询结果后再重试；连续失败时请核对渠道账单及服务配置'
        delay=6*3600 if blocked else min(30*2**min(failures,5),900)
        PaymentRefund.objects.filter(pk=pk).exclude(state='success').update(state=state,failure_count=failures,
            retry_mode='paused' if paused else current.retry_mode,
            next_check_at=None if paused or current.retry_mode=='paused' else timezone.now()+timedelta(seconds=delay),
            error_code=exc.gateway_code if known else 'RESULT_UNCONFIRMED',error_category=category,
            recovery_action=recovery,last_error=message)
        # Reflect actionable exceptions in the owning order as well.
        Order.objects.filter(pk=r.attempt.order_id,transaction_id=r.attempt.config.channel_id+':'+str(r.attempt.provider_id)).update(refund_state=state,payment_state='refund_pending')
        audit('refund_'+action,pk,actor,result='failed',before=before,after=state,error_code=exc.gateway_code if known else 'RESULT_UNCONFIRMED',source=source)
        raise
    finally: PaymentRefund.objects.filter(pk=pk).update(lease_until=None,checked_at=timezone.now())


def reconcile(order_id, scheduled=False):
    o=Order.objects.get(pk=order_id)
    for a in o.payments.filter(active_slot=1):
        if scheduled and (a.failure_count>=10 or (a.next_check_at and a.next_check_at>timezone.now())): continue
        sync(a.pk,close=o.cancel_requested or a.expires_at<=timezone.now())
    o.refresh_from_db()
    if o.refund_state in ('pending','processing','exception','blocked','unknown') and o.transaction_id:
        a=next((a for a in o.payments.filter(state='succeeded').select_related('config') if o.transaction_id==a.config.channel_id+':'+str(a.provider_id)),None)
        if a: PaymentRefund.objects.get_or_create(attempt=a,defaults={'amount':a.amount,'reason':o.refund_reason or '订单退款'})
    for r in PaymentRefund.objects.filter(attempt__order=o).exclude(state='success'):
        if scheduled and (r.retry_mode=='paused' or (r.next_check_at and r.next_check_at>timezone.now())): continue
        sync_refund(r.pk)
    o.refresh_from_db()
    return o
