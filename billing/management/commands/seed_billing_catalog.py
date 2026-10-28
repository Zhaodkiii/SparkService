from django.conf import settings
from django.core.management.base import BaseCommand
from billing.models import RechargeProduct
class Command(BaseCommand):
    help='Seed confirmed recharge mappings in draft; does not open sales.'
    def handle(self,*args,**options):
        for units,rc_id in [(60,'prod532cf0b157'),(300,'prodacc3eda3d8'),(680,'prodbb3078ef65')]:
            obj,created=RechargeProduct.objects.get_or_create(rc_project_id=settings.REVENUECAT_PROJECT_ID,apple_product_id=f'cn.zhaodk.TravelDiary.diamonds.{units}',defaults=dict(rc_product_id=rc_id,rc_package_id=f'diamonds_{units}',units=units))
            if obj.units!=units: raise ValueError('Existing units differ; refusing to overwrite purchased SKU.')
        self.stdout.write('Three recharge mappings available (new rows remain draft).')
