"""Trusted workstation/OSS-region command; never route binary uploads through the API."""
import hashlib
import io
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image
from diary_presets.models import Template
from diary_presets import storage
from material_library.models import ResourceBlob, Material, MaterialLibrary
from material_library.services import revision, publish_library
from material_library.catalog import validate_category


class Command(BaseCommand):
    help = '从已转换预设提取贴纸和背景，直接上传 OSS 并登记数据库；默认仅预览，--publish 执行'
    def add_arguments(self, parser):
        parser.add_argument('package', type=Path)
        parser.add_argument('--template', required=True)
        parser.add_argument('--publish', action='store_true')
        parser.add_argument('--overrides', type=Path)
        parser.add_argument('--export-root', type=Path, help='按系列/手帐/贴纸库或背景库导出中文目录及数据库索引')

    def handle(self, *args, **opts):
        root = opts['package'].resolve()
        template = Template.objects.get(pk=opts['template'])
        if template.audience != 'public': raise CommandError('私人定制不能发布到公共素材库')
        if not template.current_id: raise CommandError('请先发布预设')
        expected_version = template.current_id
        defaults = Path(__file__).resolve().parents[2] / 'configurations' / f'{template.pk}.json'
        overrides = json.loads(defaults.read_text()) if defaults.exists() else {}
        if opts['overrides']: overrides.update(json.loads(opts['overrides'].read_text()))
        from material_library.extraction import collect
        try: candidates = collect(root, template, overrides)
        except ValueError as exc: raise CommandError(str(exc))
        originals = {c['identity']:dict(c) for c in candidates} if opts.get('export_root') else {}
        export_rows = []
        self.stdout.write(json.dumps({'template':str(template.pk),'sticker':sum(c['type']=='sticker' for c in candidates),'background':sum(c['type']=='background' for c in candidates),'publish':opts['publish']},ensure_ascii=False))
        if not opts['publish']: return
        bucket=storage.bucket()
        def blob(data):
            digest=hashlib.sha256(data).hexdigest()
            existing=ResourceBlob.objects.filter(pk=digest).first()
            if existing:return existing
            key=storage.prefix()+'blobs/sha256/'+digest
            if not bucket.object_exists(key): bucket.put_object(key,data)
            with Image.open(io.BytesIO(data)) as image:
                return ResourceBlob.objects.get_or_create(sha256=digest,defaults=dict(object_key=key,byte_size=len(data),width=image.width,height=image.height,mime=Image.MIME[image.format]))[0]
        prepared=[]
        for c in candidates:
            c['resource_id']=blob(c.pop('data')).pk;c['thumbnail_id']=blob(c.pop('thumbnail')).pk;prepared.append(c)
        with transaction.atomic():
            template=Template.objects.select_for_update().get(pk=template.pk)
            if template.current_id != expected_version: raise CommandError('上传期间模板版本已改变，请重试')
            for typ in ('sticker','background'):
                lib,_=MaterialLibrary.objects.get_or_create(template=template,library_type=typ,defaults={'title':template.title+('贴纸库' if typ=='sticker' else '背景库')})
                rows=[];seen=set()
                for c in prepared:
                    if c['type']!=typ or c['resource_id'] in seen:continue
                    seen.add(c['resource_id'])
                    m,_=Material.objects.get_or_create(source_identity=c['identity'],defaults={'material_type':typ})
                    fields={k:v for k,v in c.items() if k not in ('identity','type')}
                    rows.append(revision(m,fields))
                version=publish_library(lib,rows,lib.current.number if lib.current_id else 0)
                self.stdout.write(f'{lib.title}: v{version.number}, {len(rows)} 项')
                export_rows.extend((lib,version,r,originals.get(r.material.source_identity)) for r in rows)
        if opts.get('export_root'):
            from material_library.exporting import export_library
            destination = export_library(opts['export_root'], template, export_rows)
            self.stdout.write('中文目录：' + str(destination))
