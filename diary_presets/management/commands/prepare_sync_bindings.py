"""Publish explicit current material bindings before a whole-book synchronization."""
import json
from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from diary_presets.models import Template
from diary_presets.views import publish
from material_library.models import TemplateMaterialLink

@transaction.atomic
def prepare(apply=False,actor=None):
    result=[]
    for book in Template.objects.select_for_update().filter(audience='public',active=True,current__isnull=False).select_related('current'):
        if book.draft!=book.current.snapshot:raise CommandError('存在未发布页面草稿，请先处理：'+book.title)
        desired={}
        for kind in ('sticker','background'):
            link=book.material_links.filter(library_type=kind).select_related('library__current').first()
            lib=link.library if link else book.material_libraries.filter(library_type=kind,active=True,deleted_at__isnull=True).select_related('current').first()
            if lib and lib.active and not lib.deleted_at and lib.current_id and lib.current.items.exists():desired[kind]=lib
        old={b.library_type:b.library_version_id for b in book.current.material_bindings.all()}
        new={k:l.current_id for k,l in desired.items()}
        if old==new:continue
        entry=dict(id=str(book.pk),title=book.title,old_version=book.current.number,bindings={k:dict(id=str(l.pk),version=l.current.number) for k,l in desired.items()})
        if apply:
            for kind in ('sticker','background'):
                lib=desired.get(kind)
                link,_=TemplateMaterialLink.objects.get_or_create(template=book,library_type=kind)
                link.library=lib;link.library_version=lib.current if lib else None;link.revision+=1;link.actor=actor;link.save()
            publish(book,actor)
            entry['new_version']=book.current.number
        result.append(entry)
    return result

class Command(BaseCommand):
    help='预览或发布清理后的模板配套绑定；不修改页面与 OSS'
    def add_arguments(self,p):p.add_argument('--apply',action='store_true')
    def handle(self,*a,**options):self.stdout.write(json.dumps(prepare(options['apply']),ensure_ascii=False))
