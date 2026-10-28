from django.core.management.base import BaseCommand
from billing.models import CurrencyEvent,StorePayment
from billing.reporting import project

class Command(BaseCommand):
    help='Rebuild reporting from processed callbacks only; never charges or grants currency.'
    def handle(self,*args,**options):
        for event in CurrencyEvent.objects.filter(state='processed',identity__isnull=False).select_related('identity').order_by('received_at','pk').iterator(chunk_size=200):
            project(event)
        self.stdout.write(f'Payment reporting rows: {StorePayment.objects.count()}')
