import logging
from celery import shared_task
from django.db.models import Q
from django.utils import timezone
from .models import Order, PaymentAttempt, PaymentRefund
from .payments import reconcile

logger = logging.getLogger(__name__)

@shared_task
def reconcile_payments():
    due = Q(next_check_at__isnull=True) | Q(next_check_at__lte=timezone.now())
    attempts = PaymentAttempt.objects.filter(due,active_slot=1,failure_count__lt=10).order_by('checked_at').values_list('order_id',flat=True)[:100]
    refunds = PaymentRefund.objects.filter(due,retry_mode='auto').exclude(state='success').order_by('checked_at').values_list('attempt__order_id',flat=True)[:100]
    requested = Order.objects.filter(refund_state='pending',payments__state='succeeded',payments__refund__isnull=True).values_list('id',flat=True)[:100]
    for pk in set(list(attempts)+list(refunds)+list(requested)):
        try: reconcile(pk,scheduled=True)
        except Exception as exc: logger.warning('Print reconciliation %s: %s',pk,type(exc).__name__)

    from .models import PaymentProbe
    from .payment_probes import sync
    for pk in PaymentProbe.objects.exclude(state__in=['closed','refunded','expired','discarded']).exclude(state='created',expires_at__gt=timezone.now()).order_by('created_at').values_list('pk',flat=True)[:20]:
        try: sync(pk)
        except Exception as exc: logger.warning('Payment probe %s: %s',pk,type(exc).__name__)
