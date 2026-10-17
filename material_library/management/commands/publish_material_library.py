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

    def handle(self, *args, **opts):
        root = opts['package'].resolve()
        manifest = json.loads((root/'package.json').read_text())
        template = Template.objects.get(pk=opts['template'])
        if not template.current_id: raise CommandError('请先发布预设')
        expected_version = template.current_id
        published_hashes = {a['sha256'] for a in template.current.snapshot['manifest']['assetTable'].values()}
        overrides = json.loads(opts['overrides'].read_text()) if opts['overrides'] else {}
        candidates = []
        for oid, path in manifest['objectTable'].items():
            object_path = (root/path).resolve()
            if not object_path.is_relative_to(root): raise CommandError('不安全对象路径')
            obj = json.loads(object_path.read_text())
            for node in obj.get('layers',[]):
                aid = node.get('assetID')
                if not aid or aid not in manifest['assetTable']: continue
                kind, sub = node.get('kind'),node.get('subcategory')
                name = node.get('name','')
                key = str(node.get('id',oid))
                override = overrides.get(key,{})
                allowed = (kind == 'background' or (obj.get('role') == 'sticker' and len(obj.get('layers',[])) == 1 and (
                    kind == 'illustration' or kind == 'photo' and sub == 'frame' or
                    kind == 'photo' and sub == 'photo_card' and any(w in name for w in ('空白','无字')) or
                    kind == 'paper' and (sub in ('route','ticket') or any(w in name for w in ('空白','无字'))))))
                if not override.get('include',allowed): continue
                kind, sub = override.get('kind',kind),override.get('subcategory',sub)
                typ = 'background' if kind == 'background' else 'sticker'
                validate_category(kind,sub,typ)
                asset = manifest['assetTable'][aid]
                file = (root/asset['path']).resolve()
                if not file.is_relative_to(root): raise CommandError('不安全资源路径')
                if asset['sha256'] not in published_hashes: raise CommandError('源素材不属于当前已发布的手帐版本')
                data = file.read_bytes()
                if hashlib.sha256(data).hexdigest()!=asset['sha256']: raise CommandError('资源摘要不符')
                if len(data) > 100_000_000: raise CommandError('资源超过大小限制')
                with Image.open(io.BytesIO(data)) as image:
                    if image.width * image.height > 50_000_000: raise CommandError('资源像素过大')
                    image.load()
                    if typ=='sticker' and ('A' not in image.getbands() or image.getchannel('A').getextrema()[0] != 0): continue
                    thumb=image.convert('RGBA');thumb.thumbnail((320,320))
                    out=io.BytesIO();thumb.save(out,format='WEBP',quality=85)
                candidates.append(dict(identity=override.get('identity',f'{template.pk}:{key}'),type=typ,name=override.get('name',name),kind=kind,subcategory=sub,
                    keywords=override.get('keywords',[template.title]),aliases=override.get('aliases',[]),data=data,thumbnail=out.getvalue(),sources=[dict(object_id=oid,layer_id=key)]))
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
