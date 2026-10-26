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
