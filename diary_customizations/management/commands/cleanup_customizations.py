"""Run in the OSS region with storage credentials. Default dry run, never delete live delivery blobs."""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from diary_customizations.models import Request,Asset,Job
from diary_customizations.storage import scope
from diary_presets.storage import bucket

class Command(BaseCommand):
    help='清理私人定制资料；默认仅列出计划，执行需 --execute（在 OSS 同地域运行）'
    def add_arguments(self,p): p.add_argument('--execute',action='store_true')
    def handle(self,*args,**opts):
        now=timezone.now();client=bucket()
        # A deletion request immediately withdraws access; bytes have a 24-hour grace period.
        targets=Request.objects.filter(Q(deleted_at__lt=now-timedelta(days=1))|
            Q(status='draft',updated_at__lt=now-timedelta(days=30))|
            Q(status__in=['completed','cancelled','rejected'],updated_at__lt=now-timedelta(days=90)))
        import oss2
        for obj in targets.iterator():
            full=bool(obj.deleted_at or obj.status=='draft')
            prefixes=[scope(obj)] if full else [scope(obj)+'inputs/',scope(obj)+'thumbnails/',scope(obj)+'staging/']
            self.stdout.write(f'{obj.pk}: {"全部云端资料" if full else "制作输入图"}')
            if not opts['execute']: continue
            # Claim expiry/deletion before storage access; all API/processor paths recheck these fields.
            if full and not obj.deleted_at:
                obj.deleted_at=now;obj.save(update_fields=['deleted_at']);obj.deliveries.update(status='withdrawn')
            for prefix in prefixes:
                for item in oss2.ObjectIterator(client,prefix=prefix): client.delete_object(item.key)
            if full:
                for e in obj.events.all(): e.message='';e.details={};e.save(update_fields=['message','details'])
                obj.submissions.update(snapshot={});obj.brief={};obj.title='已删除定制';obj.internal_note='';obj.save()
                for d in obj.deliveries.select_related('version'):
                    d.version.snapshot={};d.version.save(update_fields=['snapshot'])
                from diary_presets.models import Template
                Template.objects.filter(customization_id=obj.pk).update(title='已删除定制',draft={},description='',active=False)
                obj.jobs.update(result={},error='')
                obj.assets.update(note='',object_key='',thumbnail_key='',status='deleted')
            else: obj.assets.update(object_key='',thumbnail_key='',status='expired')
        # Orphaned and failed staging objects cannot become a delivery after expiry.
        for job in Job.objects.filter(created_at__lt=now-timedelta(days=1)).exclude(status='abandoned').exclude(kind='asset',status='ready'):
            self.stdout.write(f'staging: {job.pk}')
            if opts['execute']:
                if job.status!='ready': job.status='abandoned';job.save(update_fields=['status'])
                client.delete_object(job.object_key)
        self.stdout.write('清理执行完成' if opts['execute'] else '仅预览，未删除任何对象')
