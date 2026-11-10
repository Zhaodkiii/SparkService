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
    release_cancelled_coupon(order)
    Event.objects.create(order=order, actor=actor, action=action, message=message, details=details or {})


def reconcile(pk):
    from .payments import reconcile as run
    return run(pk)


def cancel(order, actor):
    if order.state not in ('draft', 'awaiting_review', 'queued', 'needs_revision'):
        raise Conflict('当前阶段无法直接取消，请提交售后申请')
    order.cancel_requested = True
    order.state = 'cancelled'
    if order.transaction_id:
        order.payment_state = 'refund_pending'; order.refund_state = 'pending'
        order.refund_reason = '用户或管理员取消订单'
    event(order, 'cancelled', '订单已取消' + ('，退款处理中' if order.transaction_id else ''), actor)

def release_cancelled_coupon(order):
    if not order.coupon_snapshot or order.state != 'cancelled':
        return
    if order.payment_state not in ('unpaid','not_required','refunded'):
        return
    if order.payments.filter(active_slot=1).exists() or order.events.filter(action='start').exists():
        return
    from .models import PrintCoupon, PrintEnrollment
    from .campaigns import award
    coupon_id = PrintCoupon.objects.filter(order=order).values_list('pk', flat=True).first()
    if coupon_id is None:
        return
    entry = PrintEnrollment.objects.select_for_update().filter(coupon_id=coupon_id).first()
    coupon = PrintCoupon.objects.select_for_update().filter(pk=coupon_id, order=order).first()
    if coupon:
        coupon.order=None
        coupon.save(update_fields=['order'])
        if entry and not entry.withdrawn_at and entry.approved_pages >= 20:
            award(entry,100)
