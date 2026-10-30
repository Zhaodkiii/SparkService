from datetime import timedelta
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from .models import PresetSyncTask
from .sync_protocol import SyncError, wire_environment
from .sync_engine import claim, heartbeat, fail, receiver_preflight, receiver_import
from .sync_transport import remote

ACTIVE={'preflighting','queued','checking','outcome_unknown','committed','committed_verification_pending','verifying'}


def enqueue(pk, countdown=0):
    try:run_sync_task.apply_async(args=[str(pk)],countdown=countdown)
    except Exception:
        # Durable task remains queued; beat recovery will redeliver it.
        pass


def source_step(t,token):
    if t.state=='preflighting':
        if not t.remote_preflight_id:
            capabilities=remote('GET','capabilities/')
            if capabilities.get('environment')!='production' or capabilities.get('storage')!=wire_environment():raise SyncError('OSS_ENV_MISMATCH','来源和生产 OSS 配置不一致')
            result=remote('POST','preflights/',{'snapshot':t.snapshot,'storage':wire_environment(),'request_key':t.idempotency_key})
            t.remote_preflight_id=result['id'];t.save(update_fields=['remote_preflight_id','updated_at'])
        result=remote('GET','preflights/'+t.remote_preflight_id+'/')
        t.result=result.get('result',{});t.baseline=t.result.get('target_fingerprint','')
        if result['state']=='ready':
            from django.utils.dateparse import parse_datetime
            t.state='ready';t.expires_at=parse_datetime(result['expires_at'])
        elif result['state'] in ('failed','conflict','expired'):t.state=result['state']
        t.save();return t.state=='preflighting'
    if not t.remote_id:
        # Query by deterministic business key first, including after any lost POST response.
        existing=remote('GET','imports/by-key/'+t.idempotency_key+'/')
        if existing.get('found'):
            t.remote_id=existing['id']
        else:
            if not t.actor or not t.actor.is_active or not t.actor.has_perm('diary_presets.sync_template') or not t.actor.has_perm('diary_presets.change_template'):
                raise SyncError('PERMISSION_REVOKED','同步权限已撤销，请由授权管理员重新预检')
            from .models import Template
            from .sync_protocol import snapshot_for
            if snapshot_for(Template.objects.get(pk=t.library_uuid)) != t.snapshot:
                raise SyncError('SOURCE_CHANGED','来源在确认后已变化，请重新预检')
            result=remote('POST','imports/',{'preflight_id':t.remote_preflight_id,'idempotency_key':t.idempotency_key,'content_hash':t.content_hash,'target_fingerprint':t.baseline})
            t.remote_id=result['id']
        t.save(update_fields=['remote_id','updated_at'])
    result=remote('GET','imports/'+t.remote_id+'/')
    t.result=result['result'];t.commit_status=result['commit_status'];t.state=result['state'];t.save()
    return t.state in ACTIVE


@shared_task(ignore_result=True)
def run_sync_task(pk):
    token=claim(pk)
    if not token:return
    repeat=False
    try:
        t=PresetSyncTask.objects.get(pk=pk)
        if t.state not in ACTIVE:return
        heartbeat(pk,token,attempts=t.attempts+1)
        t.refresh_from_db()
        if t.side=='source':repeat=source_step(t,token)
        else:
            from django.conf import settings
            if not settings.MATERIAL_SYNC_RECEIVER_ENABLED or settings.MATERIAL_SYNC_ENVIRONMENT_ID!='production':
                raise SyncError('RECEIVER_DISABLED','生产接收已停用，请检查配置')
            if t.state=='preflighting':receiver_preflight(t,token)
            else:receiver_import(t,token)
    except SyncError as error:
        t=PresetSyncTask.objects.get(pk=pk)
        if t.side=='source' and error.retryable:
            t.state='preflighting' if not t.remote_preflight_id or t.state=='preflighting' else 'outcome_unknown'
            failures=t.result.get('network_failures',0)+1
            t.result={**t.result,'error_code':error.code,'message':error.message,'retryable':True,'network_failures':failures,'manual_retry':failures>=3}
            if failures>=3 and t.state=='preflighting':t.state='failed'
            t.save();repeat=failures<3
        else:fail(t,error)
    except Exception:
        t=PresetSyncTask.objects.get(pk=pk)
        fail(t,SyncError('TASK_ERROR','任务执行失败，请检查服务日志或重新预检',True))
    finally:
        PresetSyncTask.objects.filter(pk=pk,lease_token=token).update(lease_until=None,lease_token='')
        current=PresetSyncTask.objects.get(pk=pk)
        if current.side=='source' and (current.state in ('ready','succeeded','failed','conflict','expired') or current.result.get('manual_retry')):
            from backoffice.content_sync import notify_source_task
            notify_source_task('template',pk)
        if repeat:
            # Fast normal polling, bounded backoff; retain slower network retries.
            delay=10 if current.result.get('network_failures') else min(5,1+current.attempts//3)
            enqueue(pk,delay)


@shared_task(ignore_result=True)
def recover_sync_tasks():
    from django.db.models import Q
    now=timezone.now()
    # HMAC nonce recovery is shared with material_library.
    PresetSyncTask.objects.filter(state='ready',expires_at__lt=now).update(state='expired')
    tasks=PresetSyncTask.objects.filter(state__in=ACTIVE).filter(Q(lease_until__isnull=True)|Q(lease_until__lt=now)).filter(updated_at__lt=now-timedelta(seconds=30)).order_by('updated_at')[:50]
    for t in tasks:
        if not t.result.get('manual_retry'):enqueue(t.pk)
