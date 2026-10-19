from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = '已停用：印制服务不再访问 OSS，旧对象由存储生命周期清理'
    def handle(self, *args, **kwargs):
        self.stdout.write(self.help)
