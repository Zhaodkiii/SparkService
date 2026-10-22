import re
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from support_center.models import Attachment,Ticket,Config,GarbageObject,HelpImage,Article,ArticleVersion,Operation
from diary_presets.storage import bucket


def image_references():
    result=set()
    contents=[content for article in Article.objects.all() for content in (article.draft,article.published)]
    contents.extend(ArticleVersion.objects.values_list('content',flat=True))
    for content in contents:result.update(re.findall(r'support-image:([0-9a-fA-F-]{36})',content.get('body','')))
    return result


class Command(BaseCommand):
    help='回收未绑定截图和超过保留期的已结束工单；默认仅预览，--execute 执行'
    def add_arguments(self,parser):parser.add_argument('--execute',action='store_true')
    def handle(self,*args,**o):
        config=Config.objects.filter(pk='traveldiary').first();days=config.retention_days if config else 180
        now=timezone.now();cutoff=now-timedelta(days=days)
        old=Ticket.objects.filter(status='closed',updated_at__lt=cutoff)
        assets=Attachment.objects.select_related('message').filter(Q(message__isnull=True,created_at__lt=now-timedelta(hours=24))|Q(message__ticket__in=old)|Q(message__redacted=True)).order_by('id')[:1000]
        count=0
        for a in assets:
            if o['execute']:
                with transaction.atomic():
                    # Same ticket->attachment lock order as replies. A concurrent reopen must be seen before removal.
                    locked_ticket=None
                    if a.message_id:
                        locked_ticket=Ticket.objects.select_for_update().filter(pk=a.message.ticket_id).first()
                    current=Attachment.objects.select_for_update().filter(pk=a.pk).first()
                    if not current:continue
                    bound=current.message
                    if bound and not a.message_id:continue  # Claimed after this batch was scanned.
                    removable=not bound or bound.redacted or (locked_ticket and locked_ticket.status=='closed' and locked_ticket.updated_at<cutoff)
                    if not removable:continue
                    bucket().delete_object(current.key);current.delete()
            count+=1
        if o['execute']:
            # Recheck under a ticket lock; do not purge a ticket reopened after the scan.
            for pk in old.values_list('pk',flat=True)[:1000]:
                with transaction.atomic():
                    ticket=Ticket.objects.select_for_update().filter(pk=pk,status='closed',updated_at__lt=cutoff).first()
                    if ticket and not ticket.messages.filter(attachments__isnull=False).exists():
                        Operation.objects.filter(result_id=pk).delete();ticket.delete()
        referenced=image_references()
        stale=HelpImage.objects.exclude(pk__in=referenced).filter(created_at__lt=now-timedelta(hours=24))
        if o['execute']:
            for pk in stale.values_list('pk',flat=True)[:1000]:
                with transaction.atomic():
                    image=HelpImage.objects.select_for_update().filter(pk=pk).first()
                    if image and str(pk) not in image_references():image.delete()
            for item in GarbageObject.objects.order_by('id')[:1000]:
                bucket().delete_object(item.key);item.delete()
        self.stdout.write(f'{"已处理" if o["execute"] else "待处理"}附件 {count} 项；保留期 {days} 天')
