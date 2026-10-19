import logging
from celery import shared_task
from django.db.models import Q
from .models import Order
from .services import reconcile

logger = logging.getLogger(__name__)


@shared_task
def reconcile_payments():
    ids = Order.objects.filter(
        (Q(payment_started=True, transaction_id__isnull=True) & ~Q(state='cancelled')) |
        Q(refund_state__in=['pending', 'processing'])
    ).order_by('updated_at').values_list('id', flat=True)[:100]
    for pk in list(ids):
        try: reconcile(pk)
        except Exception as exc: logger.warning('Print reconciliation %s: %s', pk, type(exc).__name__)
