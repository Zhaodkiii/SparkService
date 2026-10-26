from django.core.management.base import BaseCommand
from print_orders.tasks import reconcile_payments


class Command(BaseCommand):
    help = '对账微信及支付宝印制交易、取消订单和退款，遵循重试退避'

    def handle(self, *args, **kwargs):
        reconcile_payments()
