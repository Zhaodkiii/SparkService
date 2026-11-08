from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from ai_runtime.models import Delivery, ClientEvent, Audit, TestRun


class Command(BaseCommand):
    help = 'Prune AI runtime operational records older than 180 days; retain releases and bindings.'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=180)
        for model in (Delivery, ClientEvent, Audit, TestRun):
            count, _ = model.objects.filter(created_at__lt=cutoff).delete()
            self.stdout.write(f'{model.__name__}: {count}')
