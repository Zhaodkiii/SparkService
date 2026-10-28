from django.core.management.base import BaseCommand
from billing.tasks import process_pending
class Command(BaseCommand):
    help='Resume durable billing operations using the original RevenueCat keys.'
    def handle(self,*args,**options):
        process_pending()
        self.stdout.write('Billing sweep completed.')
