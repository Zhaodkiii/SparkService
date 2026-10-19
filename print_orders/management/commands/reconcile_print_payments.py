from django.core.management.base import BaseCommand
from django.db.models import Q
from print_orders.models import Order
from print_orders.services import reconcile

class Command(BaseCommand):
    help = '定时对账微信印制支付及退款；建议每分钟运行'
    def handle(self, *args, **kwargs):
        ids=Order.objects.filter(Q(payment_started=True,transaction_id__isnull=True)&~Q(state='cancelled')|Q(refund_state__in=['pending','processing'])).values_list('id',flat=True)[:500]
        for pk in ids:
            try: reconcile(pk)
            except Exception as exc:
                self.stderr.write(f'{pk}: {type(exc).__name__}')
