"""Persistent batch orchestration over existing per-resource HMAC sync protocols."""
import importlib
import uuid
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from material_library.sync_protocol import SyncError, digest
from material_library.sync_transport import source_config
from .models import ContentSyncBatch

MODULES={'template':'diary_presets','material':'material_library','font':'font_library'}

def module(kind,name):return importlib.import_module(MODULES[kind]+'.'+name)

def models_for(kind):
    m=module(kind,'models')
    return {'template':('Template','PresetSyncTask'),'material':('MaterialLibrary','MaterialSyncTask'),'font':('FontFamily','FontSyncTask')}[kind],m

def entity(kind,pk):
    names,m=models_for(kind)
    return getattr(m,names[0]).objects.select_related('current').get(pk=pk)

def task_model(kind):
    names,m=models_for(kind)
    return getattr(m,names[1])

def allowed(user):
    # Batch may include all four resource kinds and prices; restrict to existing superadmins.
    return bool(user and user.is_active and user.is_superuser)

def source_enabled():
    enabled,reason=source_config()
    if not enabled:raise SyncError('SOURCE_DISABLED',reason)

def frozen(entry):return module(entry['kind'],'sync_protocol').snapshot_for(entity(entry['kind'],entry['id']))

def batch_receipts():
    """Latest confirmed batch receipt for each resource, without sorting JSON."""
    qs=ContentSyncBatch.objects.exclude(state='preview')
    ids=list(qs.order_by('-created_at','-id').values_list('pk',flat=True))
    receipts={}
    for offset in range(0,len(ids),20):
        batches=ContentSyncBatch.objects.in_bulk(ids[offset:offset+20])
        for pk in ids[offset:offset+20]:
            for entry in batches[pk].entries:
                if entry['key'] not in receipts:
                    value=dict(entry)
                    if entry.get('via') and entry['state']=='embedded':
                        parent=next((e for e in batches[pk].entries if e['key']==entry['via']),None)
                        if parent and parent['state'] in ('failed','blocked'):value['state']='blocked'
                    receipts[entry['key']]=value
    return receipts


def sync_state(kind,obj,receipts):
    e=receipts.get(kind+':'+str(obj.pk))
    if not e:return 'not_synced'
    try:
        if e.get('via'):
            from diary_presets.sync_protocol import library_snapshot
            current=library_snapshot(obj.current) if obj.current_id else None
        else:current=module(kind,'sync_protocol').snapshot_for(obj)
        if current!=e['snapshot']:return 'pending'
    except (SyncError,ObjectDoesNotExist):return 'pending'
    if e['state']=='succeeded':return 'succeeded'
    if e['state'] in ('running','pending','embedded'):return 'running'
    return 'failed'


def catalog():
    from diary_presets.models import Template
    from material_library.models import MaterialLibrary
    from font_library.models import FontFamily
    rows=[]
    receipts=batch_receipts()
    for kind,qs in [('template',Template.objects.filter(audience='public')),('material',MaterialLibrary.objects.filter(deleted_at__isnull=True)),('font',FontFamily.objects.all())]:
        for obj in qs.select_related('current'):
            version=obj.current.number if obj.current_id else 0
            typ=obj.library_type if kind=='material' else kind
            empty=kind=='material' and obj.current_id and not obj.current.items.exists()
            unbound=kind=='material' and obj.template_id and not obj.versions.filter(template_bindings__preset_version_id=obj.template.current_id,pk=obj.current_id).exists()
            state=sync_state(kind,obj,receipts)
            sync_label={'not_synced':'未同步','pending':'本地有更新，待同步','succeeded':'已同步当前版本','running':'同步处理中','failed':'上次同步失败'}[state]
            rows.append(dict(sync_state=state,sync_label=sync_label,key=kind+':'+str(obj.pk),kind=kind,type=typ,id=str(obj.pk),title=obj.title,version=version,
                selectable=bool(obj.active and version and not empty and not unbound and state not in ('succeeded','running')),reason='未绑定到整本当前版本' if unbound else ('空素材包' if empty else ('' if obj.active and version else '未发布或已下架')),
                owner_id=str(obj.template_id) if kind=='material' and obj.template_id else None))
    for row in rows:
        if row['sync_state']=='succeeded':row['reason']='当前版本无需重复同步'
        elif row['sync_state']=='running':row['reason']='请等待当前同步任务完成'
    return rows

def make_plan(selection):
    from material_library.models import MaterialLibrary
    from billing.models import ContentOffer
    if not isinstance(selection,list) or not 1<=len(selection)<=300:raise SyncError('INVALID_SELECTION','请选择 1–300 项资源')
    entries={};visiting=set()
    def add(kind,pk,reason):
        key=kind+':'+str(pk)
        if key in entries:return
        if key in visiting:raise SyncError('DEPENDENCY_CYCLE','依赖存在循环')
        if kind not in MODULES:raise SyncError('INVALID_SELECTION','资源类型无效')
        visiting.add(key)
        obj=entity(kind,pk)
        if kind=='material' and obj.template_id:
            add('template',obj.template_id,'配套素材需随整本同步')
            if key not in entries:raise SyncError('BINDING_STALE','素材未绑定到模板当前发布版本，请先发布绑定')
            visiting.discard(key);return
        snap=module(kind,'sync_protocol').snapshot_for(obj)
        deps=[];embedded=[]
        if kind=='template':
            for lib in snap['libraries']:
                lk='material:'+lib['id']
                embedded.append(lk)
                entries[lk]=dict(key=lk,kind='material',type=lib['type'],id=lib['id'],title=lib['title'],version=lib['version'],
                    state='embedded',via=key,reason='随整本原子提交',snapshot=lib)
            # Explicit cloud font identity only; never guess a cloud font by display name.
            for ref in snap['book']['snapshot']['manifest'].get('requiredFonts',[]):
                fid=ref.get('id','')
                if fid in ('system','handwriting.lxgw.wenkai'):
                    if fid=='handwriting.lxgw.wenkai' and str(ref.get('version'))!='1.522':
                        raise SyncError('FONT_DEPENDENCY','客户端内置字体版本不匹配')
                    continue
                try: font_id=str(uuid.UUID(fid))
                except (ValueError,TypeError):raise SyncError('FONT_DEPENDENCY','未登记的字体依赖：'+str(fid))
                font=entity('font',font_id)
                if not font.current_id or str(font.current.number)!=str(ref.get('version')):
                    raise SyncError('FONT_VERSION','模板需要的字体不是当前发布版本，请先调整模板字体依赖')
                if ref.get('faceID') and ref['faceID'] not in [f['id'] for f in font.current.content['faces']]:
                    raise SyncError('FONT_FACE','模板字体字面不存在')
                add('font',font_id,'模板字体依赖');deps.append('font:'+font_id)
        policy=snap.get('initial_policy') or {}
        for grant in policy.get('bundled_grants',[]):
            lib=MaterialLibrary.objects.get(pk=grant['target_id'])
            if lib.template_id:raise SyncError('BUNDLE_DEPENDENCY','附赠包必须先作为独立包同步并配置生产价格')
            add('material',lib.pk,'收费附赠包依赖');deps.append('material:'+str(lib.pk))
        entries[key]=dict(key=key,kind=kind,type=kind if kind!='material' else obj.library_type,id=str(obj.pk),title=obj.title,
            version=snap['source_version'],snapshot=snap,state='pending',reason=reason,dependencies=deps,embedded=embedded)
        visiting.discard(key)
    try:
        for row in selection:add(row['kind'],uuid.UUID(row['id']),'手动选择')
    except SyncError:raise
    except Exception as exc:raise SyncError('PLAN_INVALID','资源缺失、未上架或依赖不完整') from exc
    # Completed automatic dependencies remain visible in the review plan, but
    # are not dispatched again. Embedded resources retain their parent lifecycle.
    receipts=batch_receipts()
    for e in entries.values():
        if e['state']!='embedded' and sync_state(e['kind'],entity(e['kind'],e['id']),receipts)=='succeeded':
            e.update(state='succeeded',reason='当前版本已同步，自动跳过')
    return list(entries.values())

def render(batch):
    entries=[]
    for entry in batch.entries:
        value={k:v for k,v in entry.items() if k!='snapshot'}
        if entry.get('task_id'):
            t=task_model(entry['kind']).objects.filter(pk=entry['task_id']).first()
            if t:value['task']=module(entry['kind'],'sync_engine').task_json(t)
        entries.append(value)
    return dict(id=str(batch.pk),state=batch.state,plan_hash=batch.plan_hash,expires_at=batch.expires_at,created_at=batch.created_at,entries=entries)

class Permission(BasePermission):
    def has_permission(self,request,view):return allowed(request.user)

class Base(APIView):
    permission_classes=[Permission]
    def handle_exception(self,exc):
        if isinstance(exc,SyncError):return Response(dict(code=exc.code,message=exc.message),status=409)
        return super().handle_exception(exc)

class Catalog(Base):
    def get(self,request):
        enabled,reason=source_config()
        return Response(dict(items=catalog(),enabled=enabled,reason=reason))

class Batches(Base):
    def get(self,request):
        # Never filesort JSON snapshots: MySQL can exceed sort_buffer_size even
        # for one large batch. Sort only lightweight identifiers, then fetch by PK.
        ids=list(ContentSyncBatch.objects.order_by('-created_at','-id').values_list('pk',flat=True)[:20])
        batches=ContentSyncBatch.objects.in_bulk(ids)
        return Response([render(batches[pk]) for pk in ids])
    def post(self,request):
        source_enabled()
        selection=request.data.get('selection')
        entries=make_plan(selection)
        receipts=batch_receipts()
        selected={row['kind']+':'+str(row['id']) for row in selection}
        if any(e['key'] in selected and sync_state(e['kind'],entity(e['kind'],e['id']),receipts)=='succeeded' for e in entries):
            raise SyncError('ALREADY_SYNCED','所选资源当前版本已同步，请刷新待同步列表')
        batch=ContentSyncBatch.objects.create(actor=request.user,entries=entries,plan_hash=digest(entries),expires_at=timezone.now()+timedelta(minutes=30))
        return Response(render(batch),status=201)

class Detail(Base):
    def get(self,request,pk):return Response(render(get_object_or_404(ContentSyncBatch,pk=pk)))

class Confirm(Base):
    @transaction.atomic
    def post(self,request,pk):
        source_enabled()
        b=get_object_or_404(ContentSyncBatch.objects.select_for_update(),pk=pk)
        if b.state!='preview':return Response(render(b))
        if request.data.get('plan_hash')!=b.plan_hash or b.expires_at<timezone.now():raise SyncError('PLAN_EXPIRED','清单已变化或过期，请重新预览')
        receipts=batch_receipts()
        for e in b.entries:
            if not e.get('via') and frozen(e)!=e['snapshot']:raise SyncError('SOURCE_CHANGED','本地发布内容已变化：'+e['title'])
            if sync_state(e['kind'],entity(e['kind'],e['id']),receipts)=='succeeded':
                e.update(state='succeeded',reason='当前版本已同步，自动跳过')
        from celery import current_app
        registered=current_app.control.inspect(timeout=2).registered() or {}
        needed={'backoffice.content_sync.run_batch'}|{MODULES[e['kind']]+'.tasks.run_sync_task' for e in b.entries if e['state']!='embedded'}
        if not any(needed<=set(tasks) for tasks in registered.values()):raise SyncError('WORKER_UNAVAILABLE','请先重启并确认本地同步 worker 在线')
        b.state='running';b.actor=request.user;b.save()
        transaction.on_commit(lambda:enqueue(b.pk))
        return Response(render(b),status=202)

class Retry(Base):
    @transaction.atomic
    def post(self,request,pk):
        source_enabled()
        b=get_object_or_404(ContentSyncBatch.objects.select_for_update(),pk=pk)
        if b.state!='partial':raise SyncError('INVALID_STATE','仅允许重试已结束批次的失败项')
        for e in b.entries:
            if e['state'] in ('failed','blocked'):
                if frozen(e)!=e['snapshot']:raise SyncError('SOURCE_CHANGED','本地资源已改变，请新建清单：'+e['title'])
                t=task_model(e['kind']).objects.filter(pk=e.get('task_id')).first()
                if t and (t.commit_status=='committed' or t.state in ('outcome_unknown','committed_verification_pending')):
                    t.result={**t.result,'manual_retry':False,'network_failures':0};t.save();e['state']='running'
                    transaction.on_commit(lambda kind=e['kind'],pk=t.pk:module(kind,'tasks').enqueue(pk))
                else:e['state']='pending';e.pop('task_id',None)
        b.state='running';b.save();transaction.on_commit(lambda:enqueue(b.pk))
        return Response(render(b),status=202)

def enqueue(pk):
    try:run_batch.apply_async(args=[str(pk)])
    except Exception:pass # periodic durable recovery

def notify_source_task(kind, task_id):
    """Wake confirmed parent batches after the child lease has been released."""
    key=str(task_id)
    for batch in ContentSyncBatch.objects.filter(state='running').order_by().only('id','entries'):
        if any(e.get('kind')==kind and e.get('task_id')==key for e in batch.entries):
            enqueue(batch.pk)


@shared_task(ignore_result=True)
def run_batch(pk, expected_updated=None):
    with transaction.atomic():
        b=ContentSyncBatch.objects.select_for_update().get(pk=pk)
        if b.state!='running':return
        # Only the newest fallback timer may extend the polling chain.
        if expected_updated and b.updated_at.isoformat()!=expected_updated:return
        if not allowed(b.actor):b.state='partial';b.save();return
        source_enabled()
        bykey={e['key']:e for e in b.entries}
        waiting=False
        in_flight=sum(e['state']=='running' for e in b.entries)
        for e in b.entries:
            if e['state'] in ('succeeded','embedded','failed','blocked'):continue
            try:
                if any(bykey[d]['state'] in ('failed','blocked') for d in e.get('dependencies',[])):
                    e.update(state='blocked',message='前置依赖未完成');continue
                if any(bykey[d]['state']!='succeeded' for d in e.get('dependencies',[])):waiting=True;continue
                if not e.get('task_id'):
                    if in_flight>=2:
                        waiting=True
                        continue
                    if frozen(e)!=e['snapshot']:raise SyncError('SOURCE_CHANGED','本地资源已变化，请新建批次')
                    active=task_model(e['kind']).objects.filter(side='source',library_uuid=e['id'],state__in=['preflighting','ready','queued','checking','committed','outcome_unknown','committed_verification_pending']).first()
                    if active:raise SyncError('TASK_IN_PROGRESS','此资源已有单项或其他批次任务，请先处理')
                    s=e['snapshot']
                    t=task_model(e['kind']).objects.create(side='source',source_environment=settings.MATERIAL_SYNC_ENVIRONMENT_ID,library_uuid=e['id'],source_version=s['source_version'],content_hash=s['content_hash'],snapshot=s,actor=b.actor,idempotency_key=uuid.uuid4().hex)
                    e.update(task_id=str(t.pk),state='running')
                    in_flight+=1
                    transaction.on_commit(lambda kind=e['kind'],tid=t.pk:module(kind,'tasks').enqueue(tid))
                else:t=task_model(e['kind']).objects.get(pk=e['task_id'])
                if t.state=='ready':
                    if frozen(e)!=e['snapshot']:raise SyncError('SOURCE_CHANGED','预检期间本地资源已变化')
                    if not t.expires_at or t.expires_at<timezone.now():raise SyncError('PREFLIGHT_EXPIRED','生产预检已过期')
                    t.state='queued';t.save()
                    transaction.on_commit(lambda kind=e['kind'],tid=t.pk:module(kind,'tasks').enqueue(tid))
                if t.state=='succeeded':
                    e['state']='succeeded'
                    in_flight-=1
                    for key in e.get('embedded',[]):bykey[key]['state']='succeeded'
                elif t.state in ('failed','conflict','expired') or t.result.get('manual_retry'):
                    e.update(state='failed',message=t.result.get('message','预检过期或任务失败'))
                    in_flight-=1
                else:
                    waiting=True
                    continue
            except SyncError as exc:e.update(state='failed',message=exc.message)
            except ObjectDoesNotExist:e.update(state='failed',message='资源或同步回执已删除，请重新预览')
        pending=[e for e in b.entries if e['state'] in ('pending','running')]
        if not pending:
            b.state='partial' if any(e['state'] in ('failed','blocked') for e in b.entries) else 'succeeded'
        b.save()
    if b.state=='running':
        try:run_batch.apply_async(args=[str(pk),b.updated_at.isoformat()],countdown=10)
        except Exception:pass

@shared_task(ignore_result=True)
def recover_batches():
    for pk in ContentSyncBatch.objects.filter(state='running',updated_at__lt=timezone.now()-timedelta(seconds=30)).values_list('pk',flat=True)[:20]:enqueue(pk)
