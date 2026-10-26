import os
from pathlib import Path
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help='初始化本机支付配置加密主密钥（不回显、不覆盖）；生产环境需安全备份该密钥'
    def handle(self, *args, **options):
        if os.getenv('PRINT_PAYMENT_ENCRYPTION_KEY'):
            self.stdout.write('已通过环境变量配置主密钥，无需初始化');return
        path=Path(os.getenv('PRINT_PAYMENT_ENCRYPTION_KEY_FILE',str(settings.BASE_DIR / '.secrets' / 'print-payment.key')))
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as stream: stream.write(Fernet.generate_key()+b'\n')
        except FileExistsError:
            self.stdout.write('主密钥已存在，保留原值');return
        self.stdout.write('支付加密主密钥已创建。请独立安全备份；不要提交到代码仓库。')
