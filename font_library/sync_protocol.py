from billing.flags import sales_enabled
"""Portable font metadata. Shared immutable OSS keys; never upload/copy resource bodies."""
import uuid
import re
from django.conf import settings
from django.utils import timezone
from material_library.sync_protocol import SyncError, canonical, digest, MAX_BYTES
from .models import *
from .storage import prefix
from .services import normalize
from billing.models import ContentOffer

def wire_environment():
    return dict(bucket=settings.ALIYUN_OSS_BUCKET,endpoint=settings.ALIYUN_OSS_ENDPOINT.rstrip('/'),prefix=prefix())

def content_hash(s):
    return digest({k:s[k] for k in ('library_id','source_version','library','resources')})

def snapshot_for(font):
    if not font.current_id or not font.active:raise SyncError('SOURCE_UNAVAILABLE','请先发布并上架字体')
    version=font.current
    resources=[dict(id=str(a.pk),kind=a.kind,object_key=a.object_key,sha256=a.sha256,byte_size=a.byte_size,mime=a.mime,metadata=a.metadata) for a in version.assets.order_by('id')]
    s=dict(schema_version=1,source_environment=settings.MATERIAL_SYNC_ENVIRONMENT_ID,target_environment='production',source_version=version.number,library_id=str(font.pk),library=version.content,resources=resources)
    offer=ContentOffer.objects.select_related('current_policy_revision').filter(target_kind='font',target_id=font.pk,state='active').first()
    if not offer or not offer.current_policy_revision_id:raise SyncError('POLICY_REQUIRED','来源字体未配置有效使用策略')
    policy=offer.current_policy_revision
    s['initial_policy']={k:getattr(policy,k) for k in ('access_mode','diamond_price','currency_code','pro_entitlement_key','terms_version')}
    s['content_hash']=content_hash(s);validate_snapshot(s);return s

def validate_snapshot(s):
    try:
        if len(canonical(s))>MAX_BYTES:raise ValueError()
        if set(s)!={'schema_version','source_environment','target_environment','source_version','library_id','library','resources','initial_policy','content_hash'}:raise ValueError()
        uuid.UUID(s['library_id'])
        if s['schema_version']!=1 or s['target_environment']!='production' or not isinstance(s['source_environment'],str) or not 1<=len(s['source_environment'])<=80:raise ValueError()
        if type(s['source_version']) is not int or s['source_version']<1:raise ValueError()
        p=s['initial_policy']
        if set(p)!={'access_mode','diamond_price','currency_code','pro_entitlement_key','terms_version'}:raise ValueError()
        from billing.pricing import PolicyInput
        form=PolicyInput(data={**p,'expected_revision':0,'change_reason':'字体首次同步策略'})
        form.is_valid(raise_exception=True)
        c=normalize(s['library'])
        if set(c)!=set(s['library']) or not c['faces'] or len(c['faces'])>30:raise ValueError()
        if not c['license_approved'] or not {'app','distribution'}.issubset(c['license_scopes']):raise ValueError()
        if not isinstance(s['resources'],list) or not 1<=len(s['resources'])<=45:raise ValueError()
        resources={};keys=set()
        for a in s['resources']:
            if set(a)!={'id','kind','object_key','sha256','byte_size','mime','metadata'}:raise ValueError()
            uuid.UUID(a['id'])
            key=a['object_key']
            if not isinstance(key,str) or len(key)>255 or not key.startswith(prefix()) or any(x in key for x in ('..','://','?','#','\\')):raise ValueError()
            standard=key.startswith((prefix()+'candidates/',prefix()+'blobs/',prefix()+'media/',prefix()+'licenses/'))
            # Verified local delivery import uses immutable family/hash paths, not upload candidates.
            delivery_prefix=prefix()+'deliveries/'+s['library_id']+'/'
            delivery=False
            if key.startswith(delivery_prefix):
                suffix=key[len(delivery_prefix):]
                parts=suffix.split('/')
                delivery=bool(len(parts)>=2 and re.fullmatch(r'[a-f0-9]{16}',parts[0]) and all(p and p not in ('.','..') for p in parts[1:]) and a['sha256'].startswith(parts[0]))
            if not standard and not delivery:
                raise SyncError('INVALID_SNAPSHOT','字体资源路径与支持的交付格式不匹配：'+str(a['kind'])+' / '+str(a['id']))
            if a['id'] in resources or key in keys:raise ValueError()
            if type(a['byte_size']) is not int or not 0<a['byte_size']<=100*1024*1024:raise ValueError()
            if not isinstance(a['sha256'],str) or len(a['sha256'])!=64 or any(x not in '0123456789abcdef' for x in a['sha256']):raise ValueError()
            allowed={'font':['font/ttf','font/otf'],'cover':['image/png','image/webp'],'preview':['image/png','image/webp'],'license':['text/plain','application/pdf']}
            if a['mime'] not in allowed[a['kind']] or not isinstance(a['metadata'],dict):raise ValueError()
            resources[a['id']]=a;keys.add(key)
        used={c['cover'],c['license_asset'],*c['previews']}
        if not c['previews'] or resources[c['cover']]['kind']!='cover' or resources[c['license_asset']]['kind']!='license':raise ValueError()
        if any(resources[p]['kind']!='preview' for p in c['previews']):raise ValueError()
        if len({f['id'] for f in c['faces']})!=len(c['faces']) or c['default_face'] not in [f['id'] for f in c['faces']]:raise ValueError()
        for face in c['faces']:
            a=resources[face['asset_id']];used.add(a['id'])
            if a['kind']!='font' or a['metadata'].get('variable') or face['postscript_name'] not in [x['postscript_name'] for x in a['metadata'].get('faces',[])]:raise ValueError()
        if used!=set(resources) or s['content_hash']!=content_hash(s):raise ValueError()
    except SyncError:raise
    except Exception:raise SyncError('INVALID_SNAPSHOT','字体清单无效、超限或资源依赖不完整')

# JSON canonical form for UUID fields in target fingerprint.
def fingerprint(s):
    from .services import canonical as json_value
    f=FontFamily.objects.select_related('current').filter(pk=s['library_id']).first()
    draft=FontDraft.objects.filter(family=f).first() if f else None
    offer=ContentOffer.objects.filter(target_kind='font',target_id=s['library_id']).first()
    state=dict(font=dict(current=f.current_id,active=f.active,state=f.state_revision,content=f.current.content if f.current_id else None,draft=draft.content if draft else None,draft_revision=draft.revision if draft else None) if f else None,
      assets=list(FontAsset.objects.filter(id__in=[a['id'] for a in s['resources']]).order_by('id').values('id','family_id','object_key','sha256','byte_size','mime','kind','metadata')),
      offer=dict(state=offer.state,policy=offer.current_policy_revision_id) if offer else None)
    return digest(json_value(state))

def inspect_target(s):
    validate_snapshot(s)
    f=FontFamily.objects.select_related('current').filter(pk=s['library_id']).first()
    if f:
        if not f.active and f.current_id:raise SyncError('TARGET_WITHDRAWN','生产字体已下架，请先在生产处理')
        d=FontDraft.objects.filter(family=f).first()
        if d and (not f.current_id or d.content!=f.current.content):raise SyncError('TARGET_DRAFT_CONFLICT','生产存在未发布字体草稿')
    for a in s['resources']:
        old=FontAsset.objects.filter(pk=a['id']).first()
        same=FontAsset.objects.filter(object_key=a['object_key']).exclude(pk=a['id']).exists()
        if same or (old and (str(old.family_id)!=s['library_id'] or any(getattr(old,k)!=v for k,v in a.items() if k!='id'))):raise SyncError('RESOURCE_METADATA_MISMATCH','生产字体资源身份或元数据冲突')
        if a['kind']=='font':
            names={x['postscript_name'] for x in a['metadata']['faces']}
            for other in FontAsset.objects.filter(kind='font').exclude(sha256=a['sha256']):
                if names & {x['postscript_name'] for x in other.metadata.get('faces',[])}:raise SyncError('FONT_NAME_CONFLICT','生产存在同 PostScript 名称的不同字体文件')
    current=snapshot_for(f)['content_hash'] if f and f.current_id else None
    if current and current!=s['content_hash']:
        baseline=FontSyncMapping.objects.filter(source_environment=s['source_environment'],library_uuid=s['library_id']).order_by('-pk').first()
        if not baseline or baseline.target_version_id!=f.current_id:raise SyncError('TARGET_CHANGED','生产字体已修改或没有同步基线')
    # Price policies and users are environment-local. Never silently create free access for paid fonts.
    offer=ContentOffer.objects.select_related('current_policy_revision').filter(target_kind='font',target_id=s['library_id']).first()
    if offer and offer.state!='active':raise SyncError('POLICY_REQUIRED','生产字体价格策略未启用，请先在生产处理')
    if offer and not offer.current_policy_revision_id:raise SyncError('POLICY_REQUIRED','生产字体有未发布价格策略，请先在生产处理')
    mode=offer.current_policy_revision.access_mode if offer else s['initial_policy']['access_mode']
    if not offer:
        if mode in ('diamond_only','pro_or_diamond') and not sales_enabled('DIAMOND_REDEMPTION_ENABLED'):raise SyncError('SALES_DISABLED','生产钻石销售未开放，不能首次同步收费字体')
        if mode in ('pro_only','pro_or_diamond') and not sales_enabled('MEMBERSHIP_SALES_ENABLED'):raise SyncError('SALES_DISABLED','生产会员服务未开放')
    if mode!='free'  and 'paid_service' not in s['library']['license_scopes']:raise SyncError('LICENSE_SCOPE','生产收费策略需要付费服务授权')
    old={x['id']:x['asset_id'] for x in f.current.content['faces']} if f and f.current_id else {}
    new={x['id']:x['asset_id'] for x in s['library']['faces']}
    n=f.current.number if f and f.current_id else 0
    if current!=s['content_hash'] and s['source_version']<=n:raise SyncError('VERSION_CONFLICT','来源字体版本不高于生产版本，禁止覆盖或回退历史字体引用')
    return dict(initial_policy=s['initial_policy'] if not offer else None,pricing_action='保留生产现有价格' if offer else '首次创建来源价格策略',no_op=current==s['content_hash'],target_version=n,next_version=n if current==s['content_hash'] else s['source_version'],added=len(new.keys()-old.keys()),removed=len(old.keys()-new.keys()),updated=sum(old[k]!=new[k] for k in old.keys()&new.keys()),count=len(new),resource_count=len(s['resources']),target_fingerprint=fingerprint(s))

def sync_summary(font):
    t=FontSyncTask.objects.filter(side='source',library_uuid=font.pk).order_by('-created_at').first()
    if not t:return {'state':'not_synced','label':'未同步'}
    state=t.state
    if state=='succeeded':
        try:
            if snapshot_for(font)['content_hash']!=t.content_hash:state='pending'
        except SyncError:state='pending'
    labels={'succeeded':'已同步','pending':'待同步','ready':'待确认','failed':'失败','conflict':'存在冲突','expired':'预检过期'}
    return dict(state=state,label=labels.get(state,'同步处理中'),target_version=t.result.get('target_version'),checked_at=t.updated_at)
