from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import Order, Event
from .domain import Conflict
from . import wechat


def event(order, action, message='', actor=None, details=None):
    previous = Order.objects.only('state').get(pk=order.pk).state
    if previous != order.state:
        order.stage_started_at = timezone.now()
    order.revision += 1
    order.save()
    Event.objects.create(order=order, actor=actor, action=action, message=message, details=details or {})


def apply_payment(order, result):
    if result.get('trade_state') != 'SUCCESS': return
    if order.total_fen <= 0 or order.payment_state == 'not_required': raise ValidationError('免费订单不接受支付交易')
    cfg = wechat.config()
    if (result.get('mchid') != cfg['MCHID'] or result.get('appid') != cfg['APPID'] or
        result.get('out_trade_no') != order.id.hex or result.get('amount', {}).get('total') != order.total_fen or
        result.get('amount', {}).get('currency') != 'CNY' or not result.get('transaction_id')):
        raise ValidationError('支付交易信息不匹配')
    if order.transaction_id:
        if order.transaction_id != result['transaction_id']: raise Conflict('支付流水冲突')
        return
    order.transaction_id = result['transaction_id']
    if order.cancel_requested or order.state == 'cancelled':
        order.payment_state = 'refund_pending'
        order.refund_state = 'pending'
        order.refund_reason = '取消订单后收到付款'
    else:
        order.payment_state = 'paid'
        order.state = 'awaiting_review'
    event(order, 'paid', '微信支付已确认')


def refresh_payment(order):
    if order.payment_started and not order.transaction_id:
        apply_payment(order, wechat.query(order))


@transaction.atomic
def reconcile(pk):
    order = Order.objects.select_for_update().get(pk=pk)
    refresh_payment(order)
    if order.state == 'draft' and order.payment_started and not order.transaction_id and order.payment_expires_at and order.payment_expires_at <= timezone.now():
        cancel(order, None)
    if order.refund_state in ('pending', 'processing'):
        result = wechat.refund(order) if order.refund_state == 'pending' else wechat.query_refund(order)
        if (result.get('out_refund_no') != 'R' + order.id.hex or
            result.get('out_trade_no') != order.id.hex or result.get('amount', {}).get('refund') != order.total_fen or
            result.get('amount', {}).get('total') != order.total_fen):
            raise ValidationError('退款交易信息不匹配')
        status = result.get('status')
        if status == 'SUCCESS':
            order.refund_state = 'success'; order.payment_state = 'refunded'
            event(order, 'refunded', '退款已完成')
        elif status in ('CLOSED', 'ABNORMAL'):
            order.refund_state = 'exception'
            event(order, 'refund_exception', '退款异常，请联系工作人员')
        elif order.refund_state != 'processing':
            order.refund_state = 'processing'; event(order, 'refunding', '退款处理中')
    return order


def cancel(order, actor):
    if order.state not in ('draft', 'awaiting_review', 'queued', 'needs_revision'):
        raise Conflict('当前阶段无法直接取消，请提交售后申请')
    if order.payment_started and not order.transaction_id:
        refresh_payment(order)
        if not order.transaction_id:
            wechat.close(order)  # 关闭成功后才允许取消；超时不猜测结果。
    order.cancel_requested = True
    order.state = 'cancelled'
    if order.transaction_id:
        order.payment_state = 'refund_pending'; order.refund_state = 'pending'
        order.refund_reason = '用户或管理员取消订单'
    event(order, 'cancelled', '订单已取消' + ('，退款处理中' if order.transaction_id else ''), actor)
