"""Explicit one-time upgrade for pre-binding catalogs; published page bytes never change."""
import json
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from diary_presets.models import Template, Event
from material_library.models import TemplateLibraryBinding, TemplateMaterialLink


@transaction.atomic
def backfill(apply=False):
    results=[]
    for template in Template.objects.select_for_update().select_related('current').filter(audience='public',active=True,current__isnull=False):
        rows=[]
        for kind in ('sticker','background'):
            if template.current.material_bindings.filter(library_type=kind).exists(): continue
            link=template.material_links.filter(library_type=kind).select_related('library_version','library').first()
            if link and not link.library_id: continue  # Explicitly unlinked: do not invent an association.
            library=link.library if link else template.material_libraries.filter(library_type=kind,active=True,deleted_at__isnull=True).first()
            version=link.library_version if link else (library.current if library else None)
            if not library or not version: continue
            if not library.active or library.deleted_at or version.library_id!=library.pk:
                raise CommandError('配套素材不可用：'+template.title)
            if library.template_id not in (None,template.pk): raise CommandError('配套素材归属冲突：'+template.title)
            rows.append(dict(type=kind,library_id=str(library.pk),version=version.number))
            if apply:
                TemplateLibraryBinding.objects.create(preset_version=template.current,library_type=kind,library_version=version)
                TemplateMaterialLink.objects.get_or_create(template=template,library_type=kind,defaults={'library':library,'library_version':version})
        if rows:
            if apply:
                template.revision+=1;template.save(update_fields=['revision'])
                Event.objects.create(template=template,action='backfill-sync-links',detail={'version':template.current.number,'bindings':rows})
            results.append(dict(id=str(template.pk),title=template.title,version=template.current.number,bindings=rows))
    return results


class Command(BaseCommand):
    help='预览或补齐旧整本发布版本缺少的配套关联，保留原版本号和页面快照'
    def add_arguments(self,parser): parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):
        self.stdout.write(json.dumps(dict(applied=options['apply'],books=backfill(options['apply'])),ensure_ascii=False))
