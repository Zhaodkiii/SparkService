"""Portable metadata protocol. No resource bodies or signed URLs cross environments."""
import hashlib
import json
import uuid
from django.conf import settings
from django.utils import timezone
from django.db.models import Q
from .models import *
from .catalog import validate_category
from diary_presets.storage import prefix

MAX_BYTES = 2 * 1024 * 1024
TERMINAL = {'ready','no_op','conflict','expired','failed','succeeded'}


class SyncError(Exception):
    def __init__(self, code, message, retryable=False):
        self.code, self.message, self.retryable = code, message, retryable
        super().__init__(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def content_hash(snapshot):
    return digest({k:snapshot[k] for k in ('library_id','library','resources','materials','revisions','items')})


def revision_fields(row):
    return dict(material_id=str(row.material_id), name=row.name, kind=row.kind,
                subcategory=row.subcategory, keywords=row.keywords, aliases=row.aliases,
                resource_sha256=row.resource_id, thumbnail_sha256=row.thumbnail_id, sources=row.sources)


def revision_key(row):
    return digest(revision_fields(row))


def snapshot_for(library):
    if library.template_id or library.library_type not in ('sticker','background'):
        raise SyncError('UNSUPPORTED_LIBRARY', '仅支持独立贴纸或背景包')
    if library.deleted_at or not library.current_id or not library.active:
        raise SyncError('SOURCE_UNAVAILABLE', '请先发布并上架素材包')
    version = library.current
    rows = list(version.items.select_related('revision__resource','revision__thumbnail','material').order_by('position','id'))
    revisions, materials, resource_ids, items = {}, {}, set(), []
    for item in rows:
        if not item.material.active:
            raise SyncError('SOURCE_UNAVAILABLE', '包内存在已下架素材')
        r=item.revision; key=revision_key(r)
        revisions[key] = dict(sync_revision_key=key, **revision_fields(r))
        materials[str(item.material_id)] = dict(id=str(item.material_id),source_identity=item.material.source_identity,type=library.library_type)
        resource_ids.update([r.resource_id,r.thumbnail_id])
        items.append(dict(material_id=str(item.material_id),sync_revision_key=key,position=len(items)))
    content=version.content
    resource_ids.update(content.get('previews',[]));resource_ids.add(content.get('cover'))
    resources=[dict(sha256=b.pk,object_key=b.object_key,byte_size=b.byte_size,width=b.width,height=b.height,mime=b.mime)
               for b in ResourceBlob.objects.filter(pk__in=resource_ids).order_by('pk')]
    snapshot=dict(schema_version=1,source_environment=settings.MATERIAL_SYNC_ENVIRONMENT_ID,target_environment='production',
                  source_version=version.number,library_id=str(library.pk),
                  library={k:content.get(k) for k in ('title','description','tags','cover','previews')},
                  resources=resources,materials=[materials[k] for k in sorted(materials)],
                  revisions=[revisions[k] for k in sorted(revisions)],items=items)
    snapshot['library']['type']=library.library_type
    snapshot['content_hash']=content_hash(snapshot)
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(s):
    """Strict allowlists bound both work and persisted metadata size."""
    from rest_framework.exceptions import ValidationError
    try:
        if len(canonical(s))>MAX_BYTES: raise ValueError()
        if set(s)!={'schema_version','source_environment','target_environment','source_version','library_id','library','resources','materials','revisions','items','content_hash'}:raise ValueError()
        if s['schema_version']!=1 or s['target_environment']!='production':raise ValueError()
        uuid.UUID(s['library_id'])
        if not isinstance(s['source_version'],int) or isinstance(s['source_version'],bool) or s['source_version']<1:raise ValueError()
        lib=s['library']
        if set(lib)!={'type','title','description','tags','cover','previews'} or lib['type'] not in ('sticker','background'):raise ValueError()
        if not isinstance(lib['title'],str) or not 1<=len(lib['title'])<=60:raise ValueError()
        if not isinstance(lib['description'],str) or len(lib['description'])>1000:raise ValueError()
        def strings(xs, count, length):
            if not isinstance(xs,list) or len(xs)>count or any(not isinstance(v,str) or len(v)>length for v in xs):raise ValueError()
        strings(lib['tags'],20,30)
        if not isinstance(lib['previews'],list) or not 1<=len(lib['previews'])<=8:raise ValueError()
        for key,maximum in [('items',500),('materials',500),('revisions',500),('resources',1009)]:
            if not isinstance(s[key],list) or not 1<=len(s[key])<=maximum:raise ValueError()
        resources={}
        for b in s['resources']:
            if set(b)!={'sha256','object_key','byte_size','width','height','mime'}:raise ValueError()
            if len(b['sha256'])!=64 or any(c not in '0123456789abcdef' for c in b['sha256']):raise ValueError()
            if b['sha256'] in resources:raise ValueError()
            if not isinstance(b['object_key'],str) or not b['object_key'].startswith(prefix()+'blobs/') or len(b['object_key'])>1024 or '..' in b['object_key'] or '://' in b['object_key']:raise ValueError()
            if any(not isinstance(b[k],int) or isinstance(b[k],bool) or b[k]<=0 for k in ('width','height','byte_size')):raise ValueError()
            if max(b['width'],b['height'])>8192 or b['byte_size']>15*1024*1024 or b['mime'] not in ('image/png','image/webp','image/jpeg'):raise ValueError()
            resources[b['sha256']]=b
        cover=resources[lib['cover']]
        if cover['width']!=cover['height'] or cover['width']<512:raise ValueError()
        if any(resources[p]['width']<750 for p in lib['previews']):raise ValueError()
        materials={}
        identities=set()
        for m in s['materials']:
            if set(m)!={'id','source_identity','type'} or m['type']!=lib['type']:raise ValueError()
            uuid.UUID(m['id'])
            if m['id'] in materials or m['source_identity'] in identities or not isinstance(m['source_identity'],str) or not 1<=len(m['source_identity'])<=240:raise ValueError()
            materials[m['id']]=m;identities.add(m['source_identity'])
        revisions={}
        validated_categories=set()
        for r in s['revisions']:
            if set(r)!={'sync_revision_key','material_id','name','kind','subcategory','keywords','aliases','resource_sha256','thumbnail_sha256','sources'}:raise ValueError()
            if r['material_id'] not in materials or r['resource_sha256'] not in resources or r['thumbnail_sha256'] not in resources:raise ValueError()
            original=resources[r['resource_sha256']];thumb=resources[r['thumbnail_sha256']]
            if original['mime'] not in ('image/png','image/webp') or max(original['width'],original['height'])>4096 or original['byte_size']>10*1024*1024:raise ValueError()
            if max(thumb['width'],thumb['height'])>256 or thumb['byte_size']>1024*1024:raise ValueError()
            if not isinstance(r['name'],str) or not 1<=len(r['name'])<=120:raise ValueError()
            category=(r['kind'],r['subcategory'])
            if category not in validated_categories:
                try:validate_category(*category,lib['type'])
                except ValueError:raise SyncError('CATEGORY_UNAVAILABLE','生产素材分类不存在或已停用')
                validated_categories.add(category)
            strings(r['keywords'],40,60);strings(r['aliases'],40,60)
            if not isinstance(r['sources'],list) or len(canonical(r['sources']))>4096:raise ValueError()
            if r['sync_revision_key']!=digest({k:v for k,v in r.items() if k!='sync_revision_key'}) or r['sync_revision_key'] in revisions:raise ValueError()
            revisions[r['sync_revision_key']]=r
        seen=set()
        for n,i in enumerate(s['items']):
            if set(i)!={'position','material_id','sync_revision_key'} or i['position']!=n:raise ValueError()
            if i['material_id'] in seen or revisions[i['sync_revision_key']]['material_id']!=i['material_id']:raise ValueError()
            seen.add(i['material_id'])
        if seen!=set(materials) or len(revisions)!=len(s['items']):raise ValueError()
        used={lib['cover'],*lib['previews']}
        for r in revisions.values():used.update([r['resource_sha256'],r['thumbnail_sha256']])
        if used!=set(resources) or s['content_hash']!=content_hash(s):raise ValueError()
        if [b['sha256'] for b in s['resources']]!=sorted(resources) or [m['id'] for m in s['materials']]!=sorted(materials) or [r['sync_revision_key'] for r in s['revisions']]!=sorted(revisions):raise ValueError()
    except (ValueError,KeyError,TypeError,AttributeError,ValidationError):
        raise SyncError('INVALID_SNAPSHOT','同步清单无效、超限或依赖不完整')


def sync_summary(lib):
    if lib.template_id and lib.current_id:
        from diary_presets.models import PresetSyncTask
        from diary_presets.sync_protocol import library_snapshot
        for parent in PresetSyncTask.objects.filter(side='source',library_uuid=lib.template_id,state='succeeded').order_by('-created_at')[:10]:
            for spec in parent.snapshot.get('libraries',[]):
                if spec['id']==str(lib.pk) and spec==library_snapshot(lib.current):
                    return {'state':'succeeded','label':'已随整本同步','task_id':str(parent.pk),'target_version':spec['version'],'checked_at':parent.updated_at}
    t=(lib._list_sync_task if hasattr(lib, '_list_sync_task') else
       MaterialSyncTask.objects.filter(side='source',library_uuid=lib.pk).order_by('-created_at', '-id').first())
    if not t:return {'state':'not_synced','label':'未同步'}
    state=t.state
    if state=='succeeded':
        try:
            if snapshot_for(lib)['content_hash']!=t.content_hash:state='pending'
        except SyncError:state='pending'
    labels={'not_synced':'未同步','pending':'待同步','preflighting':'检查中','ready':'待确认','queued':'同步中','checking':'同步中','committed':'已提交','verifying':'验收中','succeeded':'已同步','conflict':'存在冲突','expired':'预检过期','failed':'失败','outcome_unknown':'结果待确认','committed_verification_pending':'已提交待核实'}
    return {'state':state,'label':labels.get(state,state),'task_id':str(t.pk),'target_version':t.result.get('target_version'),'checked_at':t.updated_at,'stale':(timezone.now()-t.updated_at).total_seconds()>60}


def target_state(s):
    """Fingerprint includes every dependency that can invalidate a preflight."""
    lib=MaterialLibrary.objects.filter(pk=s['library_id']).select_related('current').first()
    ids=[m['id'] for m in s['materials']]
    data=dict(library=None,materials=[],resources=[],categories=[])
    if lib:
        d=LibraryDraft.objects.filter(library=lib).first()
        data['library']=dict(current=lib.current_id,active=lib.active,state=lib.state_revision,template=str(lib.template_id),type=lib.library_type,
            content=lib.current.content if lib.current_id else None,draft=d.content if d else None,draft_revision=d.revision if d else None)
    for m in Material.objects.filter(Q(pk__in=ids)|Q(source_identity__in=[m['source_identity'] for m in s['materials']])).order_by('pk'):
        latest=m.revisions.order_by('-pk').first()
        refs=list(LibraryItem.objects.filter(material=m).values_list('version_id','version__library_id').order_by('version_id'))
        data['materials'].append(dict(id=str(m.pk),identity=m.source_identity,active=m.active,type=m.material_type,latest=revision_key(latest) if latest else None,refs=[(v,str(l)) for v,l in refs]))
    data['resources']=list(ResourceBlob.objects.filter(pk__in=[b['sha256'] for b in s['resources']]).order_by('pk').values())
    data['categories']=list(MaterialCategory.objects.order_by('pk').values('kind','subcategory','active'))
    return digest(data)


def inspect_target(s):
    validate_snapshot(s)
    lib=MaterialLibrary.objects.filter(pk=s['library_id']).select_related('current').first()
    if lib:
        if lib.deleted_at or not lib.active:raise SyncError('TARGET_WITHDRAWN','生产素材包已下架，请先在生产处理')
        if lib.template_id or lib.library_type!=s['library']['type']:raise SyncError('MATERIAL_IDENTITY_CONFLICT','目标包类型或归属不同')
        d=LibraryDraft.objects.filter(library=lib).first()
        if d and (not lib.current_id or d.content!=lib.current.content):raise SyncError('TARGET_DRAFT_CONFLICT','生产存在未发布草稿')
    for b in s['resources']:
        old=ResourceBlob.objects.filter(pk=b['sha256']).first()
        if old and any(getattr(old,k)!=v for k,v in b.items() if k!='sha256'):raise SyncError('RESOURCE_METADATA_MISMATCH','生产资源元数据与来源不同')
    for spec in s['materials']:
        m=Material.objects.filter(pk=spec['id']).first()
        same=Material.objects.filter(source_identity=spec['source_identity']).first()
        if (m and (m.source_identity!=spec['source_identity'] or m.material_type!=s['library']['type'])) or (same and str(same.pk)!=spec['id']):raise SyncError('MATERIAL_IDENTITY_CONFLICT','生产素材身份冲突')
        if not m:continue
        if not m.active:raise SyncError('TARGET_WITHDRAWN','生产单张素材已下架')
        desired=next(r for r in s['revisions'] if r['material_id']==spec['id'])['sync_revision_key']
        latest=m.revisions.order_by('-pk').first()
        if latest and revision_key(latest)!=desired:
            others=LibraryItem.objects.filter(material=m).exclude(version__library_id=s['library_id']).exists()
            if others:raise SyncError('SHARED_MATERIAL_CONFLICT','更新此素材会影响其他生产包，请先处理共享引用')
            baseline=MaterialSyncMapping.objects.filter(source_environment=s['source_environment'],library_uuid=s['library_id']).order_by('-pk').first()
            if baseline:
                old=baseline.target_version.items.filter(material=m).select_related('revision').first()
                if not old or revision_key(old.revision)!=revision_key(latest):raise SyncError('TARGET_CHANGED','生产单张素材已被修改')
    current_hash=None
    if lib and lib.current_id:
        current_hash=snapshot_for(lib)['content_hash']
        baseline=MaterialSyncMapping.objects.filter(source_environment=s['source_environment'],library_uuid=s['library_id']).order_by('-pk').first()
        if current_hash!=s['content_hash'] and (not baseline or baseline.target_version_id!=lib.current_id):raise SyncError('TARGET_CHANGED','生产内容没有同步基线或已被人工修改')
    old_items={str(i.material_id):revision_key(i.revision) for i in lib.current.items.select_related('revision').all()} if lib and lib.current_id else {}
    new_items={i['material_id']:i['sync_revision_key'] for i in s['items']}
    return dict(no_op=current_hash==s['content_hash'],target_version=lib.current.number if lib and lib.current_id else 0,
        next_version=(lib.current.number if lib and lib.current_id else 0)+(current_hash!=s['content_hash']),
        added=len(new_items.keys()-old_items.keys()),removed=len(old_items.keys()-new_items.keys()),
        updated=sum(old_items[k]!=new_items[k] for k in old_items.keys()&new_items.keys()),count=len(new_items),resource_count=len(s['resources']),
        target_fingerprint=target_state(s))


def wire_environment():
    return dict(bucket=settings.ALIYUN_OSS_BUCKET,endpoint=settings.ALIYUN_OSS_ENDPOINT.rstrip('/'),prefix=prefix())
