"""Metadata-only sync over shared OSS; no object I/O during synchronization."""
from django.db import transaction
from django.utils import timezone
from .models import *
from .sync_protocol import *
# Same lease, task rendering and error semantics as the sticker sync module, isolated tables.
import uuid
from datetime import timedelta
from django.db.models import Q

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
    task=FontSyncTask.objects.get(pk=pk)
    if task.side=='target':
        FontSyncSlot.objects.get_or_create(library_uuid=uuid.UUID(int=0))
        FontSyncSlot.objects.select_for_update().get(pk=uuid.UUID(int=0))
        if FontSyncTask.objects.filter(side='target',lease_until__gt=now).count()>=2:return None
    updated=FontSyncTask.objects.filter(pk=pk).filter(Q(lease_until__isnull=True)|Q(lease_until__lt=now)).update(lease_until=now+timedelta(seconds=90),lease_token=token)
    return token if updated else None


def heartbeat(pk, token, **updates):
    if not FontSyncTask.objects.filter(pk=pk,lease_token=token).update(lease_until=timezone.now()+timedelta(seconds=90),updated_at=timezone.now(),**updates):
        raise SyncError('LEASE_LOST','任务已交由其他执行器处理',True)



def receiver_preflight(t,token):
    result=inspect_target(t.snapshot)
    t.refresh_from_db();t.result=result;t.baseline=result['target_fingerprint'];t.state='ready'
    t.expires_at=timezone.now()+timedelta(minutes=10);t.save()


def receiver_import(t,token):
    if t.commit_status=='committed':verify_committed(t);return
    s=t.snapshot
    heartbeat(t.pk,token,state='checking')
    FontSyncSlot.objects.get_or_create(library_uuid=t.library_uuid)
    with transaction.atomic():
        FontSyncSlot.objects.select_for_update().get(pk=t.library_uuid)
        locked=FontSyncTask.objects.select_for_update().get(pk=t.pk)
        if locked.lease_token!=token:raise SyncError('LEASE_LOST','同步任务租约已变化',True)
        if locked.commit_status=='committed':return
        font=FontFamily.objects.select_for_update().filter(pk=t.library_uuid).first()
        if font:list(FontDraft.objects.select_for_update().filter(family=font))
        from billing.models import ContentOffer,ContentPolicyRevision
        offer=ContentOffer.objects.select_for_update().filter(target_kind='font',target_id=t.library_uuid).first()
        actual=inspect_target(s)
        if actual['target_fingerprint']!=t.baseline:raise SyncError('TARGET_CHANGED','生产字体或价格已变化，请重新预检')
        if not font:font=FontFamily.objects.create(id=t.library_uuid,title=s['library']['title'])
        if not actual['no_op']:
            assets=[]
            for a in s['resources']:
                asset,_=FontAsset.objects.get_or_create(pk=a['id'],defaults={**{k:v for k,v in a.items() if k!='id'},'family':font})
                assets.append(asset)
            release=FontRelease.objects.create(family=font,number=actual['next_version'],content=s['library'],digest=digest(s['library']))
            release.assets.set(assets)
            font.current=release;font.title=s['library']['title'];font.active=True;font.state_revision+=1
            font.first_published_at=font.first_published_at or timezone.now();font.save()
            d,_=FontDraft.objects.get_or_create(family=font)
            d.content=s['library'];d.base_version=release.number;d.revision+=1;d.save()
        else:release=font.current
        if not offer:
            policy=s['initial_policy']
            offer=ContentOffer.objects.create(target_kind='font',target_id=font.pk,title=font.title,state='active')
            revision=ContentPolicyRevision.objects.create(offer=offer,revision=1,**policy,content_scope_snapshot={'target_kind':'font','target_id':str(font.pk),'scope':'personal_permanent'})
            offer.current_policy_revision=revision;offer.save()
        FontSyncMapping.objects.get_or_create(source_environment=t.source_environment,library_uuid=font.pk,source_version=t.source_version,content_hash=t.content_hash,defaults={'target_version':release})
        FontAudit.objects.create(family=font,action='production-sync',detail={'task_id':str(t.pk),'source_environment':t.source_environment,'source_version':t.source_version,'version':release.number,'hash':t.content_hash})
        locked.commit_status='committed';locked.state='committed';locked.result={**actual,'target_version':release.number,'message':'生产字体已提交'};locked.save()
        FontSyncSlot.objects.filter(pk=t.library_uuid).update(active_task=None)
    t.refresh_from_db();verify_committed(t)


def verify_committed(t):
    font=FontFamily.objects.select_related('current').get(pk=t.library_uuid)
    if snapshot_for(font)['content_hash']!=t.content_hash:raise SyncError('VERIFICATION_PENDING','生产已提交，字体内容待核实',True)
    t.state='succeeded';t.result={**t.result,'message':'生产字体已发布并核对，复用原 OSS 文件','count':len(t.snapshot['library']['faces']),'target_version':font.current.number};t.save()
