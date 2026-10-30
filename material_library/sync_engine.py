"""Durable receiver execution. All network validation precedes the short DB transaction."""
import uuid
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import *
from .sync_protocol import *
from .services import revision


def task_json(t):
    return dict(id=str(t.pk),library_id=str(t.library_uuid),source_version=t.source_version,
                content_hash=t.content_hash,state=t.state,commit_status=t.commit_status,result=t.result,
                expires_at=t.expires_at,updated_at=t.updated_at,created_at=t.created_at)


def fail(t, error):
    t.refresh_from_db()
    if t.commit_status=='committed':
        t.state='committed_verification_pending'
    else:
        t.state='conflict' if not error.retryable else 'failed'
    t.result={**t.result,'error_code':error.code,'message':error.message,'retryable':error.retryable}
    t.save(update_fields=['state','result','updated_at'])


@transaction.atomic
def claim(pk):
    now=timezone.now();token=uuid.uuid4().hex
    task=MaterialSyncTask.objects.get(pk=pk)
    if task.side=='target':
        MaterialSyncSlot.objects.get_or_create(library_uuid=uuid.UUID(int=0))
        MaterialSyncSlot.objects.select_for_update().get(pk=uuid.UUID(int=0))
        if MaterialSyncTask.objects.filter(side='target',lease_until__gt=now).count()>=2:return None
    updated=MaterialSyncTask.objects.filter(pk=pk).filter(Q(lease_until__isnull=True)|Q(lease_until__lt=now)).update(lease_until=now+timedelta(seconds=90),lease_token=token)
    return token if updated else None


def heartbeat(pk, token, **updates):
    if not MaterialSyncTask.objects.filter(pk=pk,lease_token=token).update(lease_until=timezone.now()+timedelta(seconds=90),updated_at=timezone.now(),**updates):
        raise SyncError('LEASE_LOST','任务已交由其他执行器处理',True)


def receiver_preflight(t, token):
    s=t.snapshot
    result=inspect_target(s)
    t.refresh_from_db();t.result=result;t.baseline=result['target_fingerprint'];t.state='ready'
    t.expires_at=timezone.now()+timedelta(minutes=10);t.save()


def receiver_import(t, token):
    if t.commit_status=='committed':
        verify_committed(t);return
    s=t.snapshot
    heartbeat(t.pk,token,state='checking')
    MaterialSyncSlot.objects.get_or_create(library_uuid=t.library_uuid)
    with transaction.atomic():
        slot=MaterialSyncSlot.objects.select_for_update().get(pk=t.library_uuid)
        locked=MaterialSyncTask.objects.select_for_update().get(pk=t.pk)
        if locked.lease_token!=token:raise SyncError('LEASE_LOST','任务执行租约已改变',True)
        if locked.commit_status=='committed':return
        list(Material.objects.select_for_update().filter(pk__in=[m['id'] for m in s['materials']]).order_by('pk'))
        lib=MaterialLibrary.objects.select_for_update().filter(pk=t.library_uuid).first()
        if lib: list(LibraryDraft.objects.select_for_update().filter(library=lib))
        actual=inspect_target(s)
        if actual['target_fingerprint']!=t.baseline:raise SyncError('TARGET_CHANGED','生产内容已改变，请重新预检')
        if not lib:lib=MaterialLibrary.objects.create(id=t.library_uuid,title=s['library']['title'],library_type=s['library']['type'])
        if not actual['no_op']:
            for b in s['resources']:
                ResourceBlob.objects.get_or_create(pk=b['sha256'],defaults={k:v for k,v in b.items() if k!='sha256'})
            mats={}
            for spec in s['materials']:
                mats[spec['id']]=Material.objects.get_or_create(pk=spec['id'],defaults={'source_identity':spec['source_identity'],'material_type':s['library']['type']})[0]
            rows={}
            for r in s['revisions']:
                existing=next((x for x in mats[r['material_id']].revisions.all() if revision_key(x)==r['sync_revision_key']),None)
                rows[r['sync_revision_key']]=existing or revision(mats[r['material_id']],dict(name=r['name'],kind=r['kind'],subcategory=r['subcategory'],keywords=r['keywords'],aliases=r['aliases'],resource_id=r['resource_sha256'],thumbnail_id=r['thumbnail_sha256'],sources=r['sources']))
            content={k:v for k,v in s['library'].items() if k!='type'}
            content['items']=[{'revision':rows[i['sync_revision_key']].pk} for i in s['items']]
            from .management_api import clean_content
            content=clean_content(content,lib,True)
            v=LibraryVersion.objects.create(library=lib,number=actual['next_version'],content=content)
            LibraryItem.objects.bulk_create([LibraryItem(version=v,revision=rows[i['sync_revision_key']],material=mats[i['material_id']],position=i['position']) for i in s['items']])
            lib.current=v;lib.title=content['title'];lib.state_revision+=1
            if lib.first_published_at is None:lib.first_published_at=timezone.now()
            lib.save()
            d,_=LibraryDraft.objects.get_or_create(library=lib,defaults={'content':content})
            d.content=content;d.base_version=v.number;d.revision+=1;d.save()
            for tag in content['tags']:MaterialTag.objects.get_or_create(title=tag)
        else:v=lib.current
        MaterialSyncMapping.objects.get_or_create(source_environment=t.source_environment,library_uuid=lib.pk,
            source_version=t.source_version,content_hash=t.content_hash,defaults={'target_version':v})
        MaterialAudit.objects.create(library=lib,action='production-sync',detail=dict(task_id=str(t.pk),source_environment=t.source_environment,source_version=t.source_version,version=v.number,content_hash=t.content_hash))
        locked.commit_status='committed';locked.state='committed';locked.result={**actual,'target_version':v.number,'message':'生产内容已提交'};locked.save()
        slot.active_task=None;slot.save()
    t.refresh_from_db();verify_committed(t)


def verify_committed(t):
    lib=MaterialLibrary.objects.select_related('current').get(pk=t.library_uuid)
    if snapshot_for(lib)['content_hash']!=t.content_hash:
        raise SyncError('VERIFICATION_PENDING','生产已提交，当前内容与预期不一致，请核实',True)
    t.state='succeeded';t.result={**t.result,'message':'生产内容已发布并核对','count':len(t.snapshot['items']),'target_version':lib.current.number}
    t.save(update_fields=['state','result','updated_at'])
