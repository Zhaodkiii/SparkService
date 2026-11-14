from django.core.management.base import BaseCommand

from ai_production.tasks import expire_usage


class Command(BaseCommand):
    help = "将超时未上报的模型调用按最低消耗记账"

    def handle(self, *args, **options):
        expire_usage()
