from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from material_library.models import MaterialUpload
from diary_presets.storage import bucket, prefix


class Command(BaseCommand):
    help='仅清理超期上传 staging 对象，不删除发布资源；默认 dry-run'
    def add_arguments(self,parser):
        parser.add_argument('--days',type=int,default=7)
        parser.add_argument('--execute',action='store_true')
    def handle(self,*args,**options):
        oss=bucket() if options['execute'] else None
        rows=MaterialUpload.objects.filter(updated_at__lt=timezone.now()-timedelta(days=max(7,options['days']))).exclude(state='expired')
        count=0
        for upload in rows.iterator():
            # Only delete the staging key; immutable ResourceBlob keys are never candidates.
            if not upload.object_key.startswith(prefix()+'material-uploads/'):continue
            if oss:
                oss.delete_object(upload.object_key)
                if upload.upload_metadata:
                    oss.delete_object(upload.object_key+'/thumbnail')
                if upload.state!='verified':upload.state='expired';upload.save(update_fields=['state'])
            count+=1
        self.stdout.write(f'{"deleted" if oss else "dry-run"}: {count} staging objects')
