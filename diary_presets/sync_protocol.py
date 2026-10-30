from billing.flags import sales_enabled
"""Whole-book metadata protocol. Immutable OSS objects never pass through Django."""
import json
import uuid
from copy import deepcopy
from types import SimpleNamespace
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from material_library.sync_protocol import SyncError, canonical, digest, wire_environment, revision_fields
from material_library.models import (MaterialLibrary, Material, MaterialRevision, ResourceBlob,
    LibraryDraft, TemplateMaterialLink, MaterialCategory)
from billing.models import ContentOffer
from .models import Template, Series, SearchTaxon, PresetSyncTask, PresetSyncMapping, Upload
from .storage import prefix

MAX_BYTES = 16 * 1024 * 1024
POLICY_FIELDS = ('access_mode','diamond_price','currency_code','pro_entitlement_key','bundled_grants','terms_version')


def portable(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def content_hash(s):
    return digest({k:s[k] for k in ('library_id','source_version','book','series','taxa','libraries','resources')})


def library_snapshot(version):
    library = version.library
    if not library.active or library.deleted_at:
        raise SyncError('DEPENDENCY_WITHDRAWN','配套素材包已下架或删除')
    items = []
    for item in version.items.select_related('revision','material').order_by('position','id'):
        if not item.material.active:
            raise SyncError('DEPENDENCY_WITHDRAWN','配套单张素材已下架')
        items.append(dict(material_id=str(item.material_id), source_identity=item.material.source_identity,
                          revision=revision_fields(item.revision)))
    content = deepcopy(version.content)
    content.pop('items', None)  # Database revision PKs are environment-local.
    return dict(id=str(library.pk), template_id=str(library.template_id) if library.template_id else None,
                type=library.library_type, title=library.title, version=version.number, content=content, items=items)


def collect_taxa(manifest):
    ids = set()
    for obj in [manifest.get('metadata',{})] + manifest.get('readingUnits',[]) + list(manifest.get('pageMetadata',{}).values()):
        for field in ('defaultLocationIDs','locationIDs','tagIDs'): ids.update(obj.get(field,[]))
    rows = {}
    while ids - rows.keys():
        pending = ids - rows.keys()
        found = list(SearchTaxon.objects.filter(pk__in=pending).values('id','dimension','name','aliases','parent_id','active','merged_into_id'))
        if len(found) != len(pending): raise SyncError('MISSING_TAXON','模板引用的地点或标签不存在')
        for row in found:
            rows[row['id']] = row
            ids.update(v for v in (row['parent_id'],row['merged_into_id']) if v)
    return [rows[k] for k in sorted(rows)]


def snapshot_for(template):
    if template.deleted_at or template.audience != 'public' or not template.active or not template.series.active or not template.current_id:
        raise SyncError('SOURCE_UNAVAILABLE','仅支持已发布、已上架的公开整本模板')
    version = template.current
    libraries = [library_snapshot(b.library_version) for b in version.material_bindings.select_related('library_version__library').order_by('library_type')]
    blobs = set()
    for library in libraries:
        if library['template_id'] not in (None,str(template.pk)):
            raise SyncError('DEPENDENCY_OWNER','配套素材属于其他模板，请先调整关联')
        for item in library['items']:
            blobs.update([item['revision']['resource_sha256'],item['revision']['thumbnail_sha256']])
        blobs.update(library['content'].get('previews',[]))
        if library['content'].get('cover'): blobs.add(library['content']['cover'])
    offer = ContentOffer.objects.select_related('current_policy_revision').filter(target_kind='template',target_id=template.pk).first()
    if offer and (offer.state!='active' or not offer.current_policy_revision_id):
        raise SyncError('POLICY_REQUIRED','来源模板价格策略尚未发布或已停用')
    policy = {k:getattr(offer.current_policy_revision,k) for k in POLICY_FIELDS} if offer else None
    s = dict(schema_version=1,source_environment=settings.MATERIAL_SYNC_ENVIRONMENT_ID,target_environment='production',
             source_version=version.number,library_id=str(template.pk),
             book=dict(title=template.title,description=template.description,position=template.position,
                       content_kind=template.content_kind,snapshot=deepcopy(version.snapshot)),
             series=dict(slug=template.series.slug,title=template.series.title,position=template.series.position),
             taxa=collect_taxa(version.snapshot['manifest']), libraries=libraries,
             resources=list(ResourceBlob.objects.filter(pk__in=blobs).order_by('pk').values()),initial_policy=policy)
    s['content_hash'] = content_hash(s)
    validate_snapshot(s)
    return s


def valid_hash(value):
    return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def valid_key(key):
    return isinstance(key,str) and key.startswith(prefix()+'blobs/') and len(key)<=1024 and not any(v in key for v in ('..','://','?','#','\\'))


def resource_inventory(s):
    snap = s['book']['snapshot']
    objects = {}
    for f in snap['manifest']['files']:
        key = snap['keys'][f['path']]
        spec = dict(object_key=key,byte_size=f['byteCount'],sha256=f['sha256'])
        if key in objects and objects[key]!=spec: raise ValueError('conflicting file identity')
        objects[key] = spec
    for blob in s['resources']:
        spec = {k:blob[k] for k in ('object_key','byte_size','sha256')}
        if spec['object_key'] in objects and objects[spec['object_key']]!=spec: raise ValueError('conflicting blob identity')
        objects[spec['object_key']] = spec
    return objects


def validate_snapshot(s):
    try:
        if not isinstance(s,dict) or len(canonical(s))>MAX_BYTES: raise ValueError()
        if set(s)!={'schema_version','source_environment','target_environment','source_version','library_id','book','series','taxa','libraries','resources','initial_policy','content_hash'}: raise ValueError()
        if s['schema_version']!=1 or s['target_environment']!='production': raise ValueError()
        if not isinstance(s['source_environment'],str) or not 1<=len(s['source_environment'])<=80: raise ValueError()
        uuid.UUID(s['library_id'])
        if type(s['source_version']) is not int or s['source_version']<1: raise ValueError()
        book=s['book'];series=s['series'];snap=book['snapshot'];manifest=snap['manifest']
        if set(book)!={'title','description','position','content_kind','snapshot'} or book['content_kind'] not in ('journal','album'): raise ValueError()
        if not isinstance(book['title'],str) or not 1<=len(book['title'])<=120 or not isinstance(book['description'],str): raise ValueError()
        if type(book['position']) is not int or book['position']<0: raise ValueError()
        if set(series)!={'slug','title','position'} or not 1<=len(series['title'])<=120 or type(series['position']) is not int or series['position']<0: raise ValueError()
        from django.core.validators import validate_slug
        validate_slug(series['slug'])
        if len(series['slug'])>50: raise ValueError()
        if set(snap)!={'manifest','pages','keys'} or manifest['format']!='TravelDiary.PresetBook': raise ValueError()
        if manifest['schemaVersion'] not in (1,2) or manifest['layerSchemaVersion'] not in (1,2): raise ValueError()
        if manifest['templateBookID']!=s['library_id'] or manifest['packageVersion']!=s['source_version']: raise ValueError()
        if manifest.get('contentKind','journal')!=book['content_kind'] or manifest.get('audience','public')!='public' or manifest.get('customizationRequestID'): raise ValueError()
        if manifest['seriesID']!=series['slug']: raise ValueError()
        if not 1<=len(snap['pages'])<=100 or len(manifest['files'])>10000: raise ValueError()
        paths=set();total=0
        from .package import relative, MAX_FILE, MAX_TOTAL
        for f in manifest['files']:
            path=relative(f['path']);key=snap['keys'][path]
            if path in paths or not valid_key(key) or not valid_hash(f['sha256']): raise ValueError()
            if type(f['byteCount']) is not int or not 0<f['byteCount']<=MAX_FILE: raise ValueError()
            paths.add(path);total+=f['byteCount']
        if total>MAX_TOTAL or paths!=set(snap['keys']): raise ValueError()
        ids=[p['data']['id'] for p in snap['pages']]
        if len(set(ids))!=len(ids) or ids!=[p['id'] for p in manifest['pages']] or manifest['coverPageID'] not in ids: raise ValueError()
        for ref,page in zip(manifest['pages'],snap['pages']):
            if ref['path'] not in paths or not set(page['files'])<=paths or ref['path'] not in page['files']: raise ValueError()
            if not set(page['data'].get('preview',{}).values())<=set(page['files']): raise ValueError()
        if not set(manifest['objectTable'].values())<=paths: raise ValueError()
        if any(a['path'] not in paths for a in manifest['assetTable'].values()): raise ValueError()
        if len(s['taxa'])>1000 or len(s['libraries'])>2 or len(s['resources'])>4000: raise ValueError()
        terms={}
        for row in s['taxa']:
            if set(row)!={'id','dimension','name','aliases','parent_id','active','merged_into_id'} or row['id'] in terms: raise ValueError()
            if row['dimension'] not in ('location','theme','style','usage') or not 1<=len(row['id'])<=120 or not 1<=len(row['name'])<=120 or type(row['active']) is not bool: raise ValueError()
            if not isinstance(row['aliases'],list) or len(row['aliases'])>100 or any(not isinstance(v,str) or len(v)>120 for v in row['aliases']): raise ValueError()
            terms[row['id']]=SimpleNamespace(**row)
        for row in s['taxa']:
            for field in ('parent_id','merged_into_id'):
                seen={row['id']};node=row
                while node[field]:
                    if node[field] not in terms or node[field] in seen: raise ValueError()
                    seen.add(node[field]);node=vars(terms[node[field]])
        from .search import documents
        documents(SimpleNamespace(id=s['library_id'],title=book['title'],position=book['position'],content_kind=book['content_kind'],series=SimpleNamespace(slug=series['slug'])),snap,terms)
        resources={}
        for blob in s['resources']:
            if set(blob)!={'sha256','object_key','byte_size','width','height','mime'} or not valid_hash(blob['sha256']) or not valid_key(blob['object_key']): raise ValueError()
            if blob['sha256'] in resources or any(type(blob[k]) is not int or blob[k]<=0 for k in ('byte_size','width','height')): raise ValueError()
            if blob['byte_size']>MAX_FILE or max(blob['width'],blob['height'])>16384 or blob['mime'] not in ('image/png','image/jpeg','image/webp'): raise ValueError()
            resources[blob['sha256']]=blob
        used=set();types=set();materials={}
        for lib in s['libraries']:
            if set(lib)!={'id','template_id','type','title','version','content','items'}: raise ValueError()
            uuid.UUID(lib['id'])
            if lib['template_id'] not in (None,s['library_id']) or lib['type'] not in ('sticker','background') or lib['type'] in types: raise ValueError()
            types.add(lib['type'])
            if not 1<=len(lib['title'])<=120 or type(lib['version']) is not int or lib['version']<1 or len(lib['items'])>1000: raise ValueError()
            if set(lib['content'])-{'title','description','tags','cover','previews'}: raise ValueError()
            used.update(lib['content'].get('previews',[]))
            if lib['content'].get('cover'): used.add(lib['content']['cover'])
            seen=set()
            for item in lib['items']:
                if set(item)!={'material_id','source_identity','revision'} or item['material_id'] in seen: raise ValueError()
                uuid.UUID(item['material_id']);seen.add(item['material_id'])
                if not isinstance(item['source_identity'],str) or not 1<=len(item['source_identity'])<=240: raise ValueError()
                r=item['revision']
                if set(r)!={'material_id','name','kind','subcategory','keywords','aliases','resource_sha256','thumbnail_sha256','sources'} or r['material_id']!=item['material_id']: raise ValueError()
                if not 1<=len(r['name'])<=120 or len(r['kind'])>32 or len(r['subcategory'])>32: raise ValueError()
                for field in ('keywords','aliases'):
                    if not isinstance(r[field],list) or len(r[field])>40 or any(not isinstance(v,str) or len(v)>60 for v in r[field]): raise ValueError()
                if not isinstance(r['sources'],list) or len(canonical(r['sources']))>4096: raise ValueError()
                if item['material_id'] in materials and materials[item['material_id']]!=item: raise ValueError()
                materials[item['material_id']]=item
                used.update([r['resource_sha256'],r['thumbnail_sha256']])
        if used!=set(resources): raise ValueError()
        resource_inventory(s)
        if s['initial_policy'] is not None:
            policy=s['initial_policy']
            if set(policy)!=set(POLICY_FIELDS): raise ValueError()
            from billing.pricing import PolicyInput
            # Dependency existence is checked at the destination, not during wire parsing.
            form=PolicyInput(data={**policy,'bundled_grants':[],'expected_revision':0,'change_reason':'整本同步首次策略'})
            form.is_valid(raise_exception=True)
            if not isinstance(policy['bundled_grants'],list) or len(policy['bundled_grants'])>30: raise ValueError()
            for grant in policy['bundled_grants']:
                if set(grant)!={'target_kind','target_id'} or grant['target_kind']!='sticker_library': raise ValueError()
                uuid.UUID(grant['target_id'])
        if s['content_hash']!=content_hash(s): raise ValueError()
    except SyncError: raise
    except Exception as exc:
        raise SyncError('INVALID_SNAPSHOT','整本模板清单无效、超限或依赖不完整') from exc


def target_state(s):
    template=Template.objects.select_related('current','series').filter(pk=s['library_id']).first()
    library_ids=[l['id'] for l in s['libraries']]
    material_ids=[i['material_id'] for l in s['libraries'] for i in l['items']]
    offers=ContentOffer.objects.filter(Q(target_kind='template',target_id=s['library_id']) | Q(target_kind='sticker_library',target_id__in=library_ids))
    data=dict(template=portable(list(Template.objects.filter(pk=s['library_id']).values())),
              current=template.current.snapshot if template and template.current_id else None,
              series=list(Series.objects.filter(slug=s['series']['slug']).values()),
              taxa=list(SearchTaxon.objects.filter(pk__in=[t['id'] for t in s['taxa']]).order_by('pk').values()),
              libraries=portable(list(MaterialLibrary.objects.filter(pk__in=library_ids).order_by('pk').values())),
              drafts=portable(list(LibraryDraft.objects.filter(library_id__in=library_ids).order_by('pk').values())),
              materials=portable(list(Material.objects.filter(pk__in=material_ids).order_by('pk').values())),
              revisions=portable(list(MaterialRevision.objects.filter(material_id__in=material_ids).order_by('pk').values())),
              resources=list(ResourceBlob.objects.filter(pk__in=[b['sha256'] for b in s['resources']]).order_by('pk').values()),
              offers=portable(list(offers.order_by('pk').values('id','state','current_policy_revision_id'))),
              links=portable(list(TemplateMaterialLink.objects.filter(template_id=s['library_id']).order_by('pk').values())))
    return digest(data)


def inspect_target(s):
    validate_snapshot(s)
    template=Template.objects.select_related('current','series').filter(pk=s['library_id']).first()
    if template:
        if template.audience!='public' or template.content_kind!=s['book']['content_kind']: raise SyncError('IDENTITY_CONFLICT','生产模板身份或类型不同')
        if template.deleted_at or not template.active or not template.series.active: raise SyncError('TARGET_WITHDRAWN','生产模板或系列已停用')
        if not template.current_id or template.draft!=template.current.snapshot: raise SyncError('TARGET_DRAFT_CONFLICT','生产存在未发布整本草稿')
        if Upload.objects.filter(template=template).exclude(status__in=['done','published','failed','cancelled','ready','conflict']).exists(): raise SyncError('UPLOAD_IN_PROGRESS','生产模板有未完成上传')
        bindings={b.library_type:(b.library_version.library_id,b.library_version_id) for b in template.current.material_bindings.select_related('library_version')}
        links={l.library_type:(l.library_id,l.library_version_id) for l in template.material_links.filter(library__isnull=False)}
        desired={l['type']:(l['id'],l['version']) for l in s['libraries']}
        for link in template.material_links.filter(library__isnull=False).select_related('library_version'):
            if link.library_type not in bindings and desired.get(link.library_type)!=(str(link.library_id),link.library_version.number if link.library_version_id else None):
                raise SyncError('TARGET_DRAFT_CONFLICT','生产配套素材关联有未发布修改')
            if link.library_type in bindings and (link.library_id,link.library_version_id)!=bindings[link.library_type]:
                raise SyncError('TARGET_DRAFT_CONFLICT','生产配套素材关联有未发布修改')
    series=Series.objects.filter(slug=s['series']['slug']).first()
    if series and (not series.active or series.title!=s['series']['title'] or series.position!=s['series']['position']): raise SyncError('SERIES_CONFLICT','生产系列已停用或名称不同，请先处理')
    for row in s['taxa']:
        old=SearchTaxon.objects.filter(pk=row['id']).values(*row.keys()).first()
        if (old and old!=row) or SearchTaxon.objects.filter(dimension=row['dimension'],name=row['name']).exclude(pk=row['id']).exists(): raise SyncError('TAXON_CONFLICT','生产地点或标签与来源不一致')
    for blob in s['resources']:
        old=ResourceBlob.objects.filter(pk=blob['sha256']).values().first()
        if old and old!=blob: raise SyncError('RESOURCE_METADATA_MISMATCH','生产资源元数据不同')
    for lib in s['libraries']:
        old=MaterialLibrary.objects.filter(pk=lib['id']).first()
        if old:
            if old.library_type!=lib['type'] or (str(old.template_id) if old.template_id else None)!=lib['template_id']: raise SyncError('DEPENDENCY_CONFLICT','配套素材包身份或归属不同')
            if old.deleted_at or not old.active: raise SyncError('DEPENDENCY_WITHDRAWN','生产配套素材已下架')
            existing=old.versions.filter(number=lib['version']).first()
            if existing and library_snapshot(existing)!=lib: raise SyncError('DEPENDENCY_VERSION_CONFLICT','生产已有不同内容的同号配套素材版本')
        for item in lib['items']:
            material=Material.objects.filter(pk=item['material_id']).first()
            if Material.objects.filter(source_identity=item['source_identity']).exclude(pk=item['material_id']).exists(): raise SyncError('DEPENDENCY_CONFLICT','素材稳定身份冲突')
            if material:
                if material.source_identity!=item['source_identity'] or material.material_type!=lib['type'] or not material.active: raise SyncError('DEPENDENCY_CONFLICT','生产素材身份或状态不同')
                if material.revisions.exists() and not any(revision_fields(r)==item['revision'] for r in material.revisions.all()): raise SyncError('SHARED_MATERIAL_CONFLICT','配套单张素材发生变化，请先同步或处理共享引用')
            from material_library.catalog import validate_category
            try: validate_category(item['revision']['kind'],item['revision']['subcategory'],lib['type'])
            except ValueError: raise SyncError('CATEGORY_UNAVAILABLE','生产配套素材分类不存在或停用')
    current=snapshot_for(template)['content_hash'] if template and template.current_id else None
    # Legacy catalog imports have no sync mapping. Adopt only byte-for-byte identical
    # book snapshots at the same version; missing frozen dependency bindings may be added.
    adopt_existing=False
    missing_bindings=[]
    if template and template.current_id and template.current.number==s['source_version']:
        book_matches=(template.current.snapshot==s['book']['snapshot'] and
            all(getattr(template,k)==s['book'][k] for k in ('title','description','position','content_kind')) and
            template.series.slug==s['series']['slug'])
        desired={l['type']:l for l in s['libraries']}
        existing={b.library_type:library_snapshot(b.library_version) for b in template.current.material_bindings.select_related('library_version__library')}
        dependencies_match=all(kind in desired and spec==desired[kind] for kind,spec in existing.items())
        if book_matches and dependencies_match:
            adopt_existing=True
            missing_bindings=sorted(desired.keys()-existing.keys())
    if current and current!=s['content_hash'] and not adopt_existing:
        baseline=PresetSyncMapping.objects.filter(source_environment=s['source_environment'],library_uuid=s['library_id']).order_by('-pk').first()
        if not baseline or baseline.target_version_id!=template.current_id or baseline.content_hash!=current: raise SyncError('TARGET_CHANGED','生产整本内容被修改或没有同步基线')
    number=template.current.number if template and template.current_id else 0
    if current!=s['content_hash'] and not adopt_existing and s['source_version']<=number: raise SyncError('VERSION_CONFLICT','来源版本不高于生产，禁止覆盖历史版本')
    offer=ContentOffer.objects.select_related('current_policy_revision').filter(target_kind='template',target_id=s['library_id']).first()
    if offer and (offer.state!='active' or not offer.current_policy_revision_id): raise SyncError('POLICY_REQUIRED','生产价格策略未发布或已停用')
    policy=s['initial_policy'] if not offer else None
    if policy:
        from billing.pricing import PolicyInput
        form=PolicyInput(data={**policy,'expected_revision':0,'change_reason':'整本同步首次策略'})
        if not form.is_valid(): raise SyncError('POLICY_DEPENDENCY','首次价格策略依赖的附赠贴纸包尚未就绪，请先同步并配置其生产价格')
        mode=policy['access_mode']
        if mode in ('diamond_only','pro_or_diamond') and not sales_enabled('DIAMOND_REDEMPTION_ENABLED'): raise SyncError('SALES_DISABLED','生产钻石销售未开放')
        if mode in ('pro_only','pro_or_diamond') and not sales_enabled('MEMBERSHIP_SALES_ENABLED'): raise SyncError('SALES_DISABLED','生产会员服务未开放')
    old={p['data']['id']:p for p in template.current.snapshot['pages']} if template and template.current_id else {}
    new={p['data']['id']:p for p in s['book']['snapshot']['pages']}
    return dict(adopt_existing=adopt_existing,missing_bindings=missing_bindings,no_op=current==s['content_hash'],target_version=number,next_version=number if current==s['content_hash'] else s['source_version'],
                count=len(new),added=len(new.keys()-old.keys()),removed=len(old.keys()-new.keys()),updated=sum(old[k]!=new[k] for k in old.keys()&new.keys()),
                library_count=len(s['libraries']),resource_count=len(resource_inventory(s)),target_fingerprint=target_state(s),
                initial_policy=policy,pricing_action='保留生产现有价格' if offer else ('首次创建来源价格策略' if policy else '沿用模板现有默认访问规则'))


def sync_summary(template):
    task=PresetSyncTask.objects.filter(side='source',library_uuid=template.pk).order_by('-created_at').first()
    if not task: return dict(state='not_synced',label='未同步')
    state=task.state
    if state=='succeeded':
        try:
            if snapshot_for(template)['content_hash']!=task.content_hash: state='pending'
        except SyncError: state='pending'
    labels={'succeeded':'已同步','pending':'待同步','ready':'待确认','conflict':'存在冲突','failed':'失败','expired':'预检过期','outcome_unknown':'结果待确认','committed_verification_pending':'已提交待核实'}
    return dict(state=state,label=labels.get(state,'同步处理中'),task_id=str(task.pk),target_version=task.result.get('target_version'))
