"""Initialize/rebuild search without publishing inferred content."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from diary_presets.models import Template, SearchTaxon, Event
from diary_presets.reading_units import suggest
from diary_presets.search import index_version, bump

SEEDS = [
 ('loc-suzhou','location','苏州',['蘇州','suzhou'],None),
 ('loc-shizilin','location','狮子林',['獅子林','shizilin'],'loc-suzhou'),
 ('loc-zhuozhengyuan','location','拙政园',['拙政園','zhuozhengyuan'],'loc-suzhou'),
 ('loc-dushuhu','location','独墅湖',['獨墅湖'],'loc-suzhou'),
 ('loc-yangchenghu','location','阳澄湖',['陽澄湖'],'loc-suzhou'),
 ('loc-shanghai','location','上海',['shanghai'],None),
 ('loc-zhoushan','location','舟山',['zhoushan'],None),
 ('loc-wugongshan','location','武功山',['wugongshan'],None),
 ('theme-garden','theme','园林',['園林','yuanlin'],None),
 ('theme-boat','theme','船游',['船遊'],None),
 ('theme-lake','theme','湖泊',[],None),('theme-bookstore','theme','书店',['書店'],None),
 ('theme-hiking','theme','徒步',[],None),('theme-birthday','theme','生日纪念',['生日紀念'],None),
 ('theme-family','theme','亲子成长',['親子成長'],None),('theme-romance','theme','爱情纪念',['愛情紀念'],None),
 ('style-retro','style','复古',['復古'],None),('usage-photo-wall','usage','照片墙',['照片牆'],None),
 ('usage-opening','usage','开篇',['開篇'],None),
]

class Command(BaseCommand):
    help = '生成搜索索引与待确认配对；默认只预览，--apply 写入，绝不自动确认或发布'
    def add_arguments(self, parser):
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--template')
        parser.add_argument('--backup',type=Path)
    def handle(self,*args,**options):
        qs=Template.objects.filter(audience='public',current__isnull=False).select_related('current','series').order_by('id')
        if options['template']:qs=qs.filter(id=options['template'])
        ids=list(qs.values_list('id',flat=True))
        if options['apply'] and not options['backup']:raise CommandError('--apply 必须提供 --backup 目录')
        if options['apply']:
            options['backup'].mkdir(parents=True,exist_ok=True)
        with transaction.atomic():
            if options['apply']:
                for key,dimension,name,aliases,parent in SEEDS:
                    SearchTaxon.objects.get_or_create(id=key,defaults=dict(dimension=dimension,name=name,aliases=aliases,parent_id=parent))
            for key in ids:
                obj=Template.objects.select_for_update().select_related('current','series').get(pk=key)
                if options['apply']:
                    backup=options['backup']/(str(obj.id)+f'-r{obj.revision}.json')
                    if not backup.exists():
                        backup.write_text(json.dumps({'template_id':str(obj.id),'revision':obj.revision,'draft':obj.draft},ensure_ascii=False))
                manifest=obj.draft['manifest']
                if not manifest.get('readingUnits'):
                    suggested=suggest(manifest)
                    pairs=sum(u['kind']=='spread' for u in suggested['readingUnits'])
                    if options['apply']:
                        obj.draft['manifest']=suggested;obj.revision+=1;obj.save(update_fields=['draft','revision'])
                        Event.objects.create(template=obj,action='initialize_search',detail={'pending_pairs':pairs,'revision':obj.revision})
                    self.stdout.write(f'{obj.title}: {pairs} 组待确认配对')
                if options['apply']:index_version(obj,obj.current)
            if options['apply']:bump()
        self.stdout.write('已写入草稿与索引；未发布候选内容。' if options['apply'] else '仅预览，未写入；添加 --apply --backup 目录后初始化。')
