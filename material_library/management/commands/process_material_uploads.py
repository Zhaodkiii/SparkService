from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help='已停用：素材上传由浏览器处理图片，API 使用 OSS HEAD/COPY 完成确认'
    def add_arguments(self,parser):
        parser.add_argument('--limit',type=int,default=20)
        parser.add_argument('--watch',action='store_true')
    def handle(self,*args,**options):
        raise CommandError('无需独立处理服务，请停止旧任务并使用新版后台直接上传原图和缩略图。')
