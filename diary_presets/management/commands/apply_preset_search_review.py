"""Publish an explicitly reviewed, version-bound metadata manifest without uploading assets."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from diary_presets.models import Template, Series, SearchTaxon, Event
from diary_presets.reading_units import validate
from diary_presets.views import publish

class Command(BaseCommand):
    help = '应用已核对的跨页元数据清单；默认只预览，--apply 需指定备份目录'
    def add_arguments(self,parser):
        parser.add_argument('review',type=Path)
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--backup',type=Path)
    def handle(self,*args,**options):
        review=json.loads(options['review'].read_text())
        if options['apply'] and not options['backup']:raise CommandError('必须提供 --backup 目录')
        if options['apply']:options['backup'].mkdir(parents=True,exist_ok=True)
        with transaction.atomic():
            if options['apply']:
                for term in review.get('terms',[]):
                    old=SearchTaxon.objects.filter(pk=term['id']).first()
                    if not old:SearchTaxon.objects.create(**term)
                    elif old.name!=term['name'] or old.dimension!=term['dimension']:raise CommandError('词典身份冲突: '+term['id'])
            for item in review['books']:
                obj=Template.objects.select_for_update().select_related('current','series').get(pk=item['template_id'],audience='public')
                fields=('readingUnits','pageMetadata','metadata')
                target={k:item[k] for k in fields}
                if obj.current and all(obj.current.snapshot['manifest'].get(k)==target[k] for k in fields) and obj.series.slug==item['series']:
                    self.stdout.write(obj.title+': 已应用，跳过');continue
                if not obj.current or obj.current.number!=item['base_version'] or obj.revision!=item['draft_revision']:
                    raise CommandError(obj.title+': 内容已变化，请重新核对，不覆盖')
                manifest=obj.draft['manifest'].copy();manifest.update(target,schemaVersion=2);validate(manifest)
                self.stdout.write(f"{obj.title}: 确认 {sum(bool(u.get('searchEnabled')) for u in target['readingUnits'])} 个可搜索跨页")
                if not options['apply']:continue
                backup=options['backup']/(str(obj.id)+'.json')
                if not backup.exists():backup.write_text(json.dumps({'template_id':str(obj.id),'series':obj.series.slug,'current_version':obj.current.number,'revision':obj.revision,'draft':obj.draft,'series_states':list(Series.objects.values('id','slug','active'))},ensure_ascii=False))
                series=Series.objects.get(slug=item['series'])
                if not series.active:series.active=True;series.save(update_fields=['active'])
                obj.series=series;obj.draft['manifest']=manifest
                Event.objects.create(template=obj,action='confirm_search_review',detail={'review_id':review['review_id'],'source':review['source'],'base_version':item['base_version']})
                publish(obj,None)
        self.stdout.write('已发布元数据，原素材与历史版本保留。' if options['apply'] else '仅预览，未修改数据库。')
