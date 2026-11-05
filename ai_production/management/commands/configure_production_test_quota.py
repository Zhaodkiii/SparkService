from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from ai_production.models import ProductionPolicy


class Command(BaseCommand):
    help = "创建经过确认的 5 小时 3 次、7 天 10 次测试策略"

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("仅可在 DEBUG 测试环境运行")
        policy, created = ProductionPolicy.objects.get_or_create(
            name="制作额度联调 3/10",
            defaults={"short_limit": 3, "weekly_limit": 10, "reason": "用户确认的联调配置"},
        )
        self.stdout.write(f"策略 {policy.pk}，created={created}")
