"""Extract only reachable resources from pages present in the published preset."""
import hashlib
import io
import json
from PIL import Image
from .catalog import legacy_category, validate_category


def collect(root, template, overrides):
    root = root.resolve()
    def read(path):
        file=(root/path).resolve()
        if not file.is_relative_to(root): raise ValueError('不安全源文件路径')
        return file
    manifest=json.loads(read('package.json').read_text())
    snapshot=template.current.snapshot['manifest']
    hashes={a['sha256'] for a in snapshot['assetTable'].values()}
    published={p['id']:p['title'] for p in snapshot['pages']}
    objects={oid:json.loads(read(path).read_text()) for oid,path in manifest['objectTable'].items()}
    sources={}
    matched_pages=set()
    for ref in manifest['pages']:
        page=json.loads(read(ref['path']).read_text())
        pid=next((p for p in published if p == page['id'] or p.endswith('-'+page['id'])),None)
        if pid is None: continue
        matched_pages.add(pid)
        visited=set()
        def walk(oid):
            if oid in visited: return
            visited.add(oid)
            sources.setdefault(oid,[]).append(dict(page_id=pid,page_title=published[pid]))
            for child in objects[oid]['layers']:
                if child.get('contentID'): walk(child['contentID'])
        walk(page['rootContentID'])
    if matched_pages != set(published): raise ValueError('源包未覆盖当前已发布的全部页面，禁止覆盖素材库')
    candidates=[]
    for oid,obj in objects.items():
        if oid not in sources: continue
        for node in obj.get('layers',[]):
            aid=node.get('assetID')
            if not aid or aid not in manifest['assetTable']:continue
            name=node.get('name','');key=str(node.get('id',oid));override=overrides.get(key,{})
            if ('�' in name or any(0x80 <= ord(c) <= 0x9f for c in name)) and not override.get('include',False): continue
            kind,sub=node.get('kind'),node.get('subcategory')
            if not sub:
                kind,sub=legacy_category(name,kind)
                if name.startswith(('图层 ', '照片组_', '照片组件_', 'photo_照片_')): kind,sub='photo','fixed'
                if name.startswith('插画_'):
                    kind='illustration'
                    sub='botanical' if any(w in name for w in ('花','叶','枝')) else 'scene' if any(w in name for w in ('群岛','山','城','建筑')) else 'object'
                if name.startswith(('群岛_', '航线_')):kind,sub='illustration','scene'
                if name.startswith(('船只_', '罗盘_', '海鸥_')):kind,sub='illustration','object'
                if name.startswith('便签_'):kind,sub='paper','note'
            kind,sub=override.get('kind',kind),override.get('subcategory',sub)
            allowed=(kind=='background' or (obj.get('role')=='sticker' and len(obj.get('layers',[]))==1 and (
                kind=='illustration' or kind=='photo' and sub=='frame' or
                kind=='photo' and sub=='photo_card' and any(w in name for w in ('空白','无字')) or
                kind=='paper' and (sub in ('route','ticket') or any(w in name for w in ('空白','无字','书写','记录','便签'))))))
            if not override.get('include',allowed):continue
            typ='background' if kind=='background' else 'sticker'
            validate_category(kind,sub,typ)
            asset=manifest['assetTable'][aid]
            if asset['sha256'] not in hashes:raise ValueError('源素材与当前发布版本不符')
            data=read(asset['path']).read_bytes()
            if hashlib.sha256(data).hexdigest()!=asset['sha256']:raise ValueError('资源摘要不符')
            if len(data)>100_000_000:raise ValueError('资源过大')
            with Image.open(io.BytesIO(data)) as image:
                if image.width*image.height>50_000_000:raise ValueError('资源像素过大')
                image.load()
                if typ=='sticker' and ('A' not in image.getbands() or image.getchannel('A').getextrema()[0]!=0):continue
                thumb=image.convert('RGBA');thumb.thumbnail((320,320))
                output=io.BytesIO();thumb.save(output,format='WEBP',quality=85)
            candidates.append(dict(identity=override.get('identity',f'{template.pk}:{key}'),type=typ,name=override.get('name',name),kind=kind,subcategory=sub,
                keywords=override.get('keywords',[template.title]),aliases=override.get('aliases',[]),data=data,thumbnail=output.getvalue(),
                sources=[dict(**s,object_id=oid,layer_id=key) for s in sources[oid]]))
    return candidates
