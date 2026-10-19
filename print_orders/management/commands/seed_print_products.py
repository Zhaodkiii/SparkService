"""幂等建立免费 A5 / ISO B5 草稿；不会伪造纸张、打样、配送或售后配置。"""
import uuid
from django.core.management.base import BaseCommand
from django.db import transaction
from print_orders.models import Product

PRESETS = [('A5',148,210),('B5（ISO）',176,250)]

class Command(BaseCommand):
    help = '建立 A5、ISO B5 免费印制规格；已存在的规格不覆盖'
    @transaction.atomic
    def handle(self,*args,**kwargs):
        for title,width,height in PRESETS:
            identifier=uuid.uuid5(uuid.NAMESPACE_URL,f'traveldiary:print:{width}x{height}')
            obj,created=Product.objects.get_or_create(id=identifier,defaults=dict(
                title=title,width_mm=width,height_mm=height,free_printing=True,
                base_fen=0,page_fen=0,shipping_fen=0,paper='',binding='',
                description=f'{title} · {width} × {height} mm；当前免费印制。',
                active=False,proof_approved=False,regions=[],terms=''))
            self.stdout.write(f'{obj.title}: {"已创建免费规格（待配置开放）" if created else "已存在，保留当前设置"}')
