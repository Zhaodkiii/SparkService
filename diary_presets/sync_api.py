import uuid
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from rest_framework import serializers
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

class AuthView(APIView):
    permission_classes = [IsAuthenticated]
from .models import *
from .sync_protocol import *
from .sync_engine import task_json
from .sync_transport import authorize, source_config
from .tasks import enqueue


def worker_ready():
    from celery import current_app
    try:
        registered=current_app.control.inspect(timeout=1).registered() or {}
        return any('diary_presets.tasks.run_sync_task' in names for names in registered.values())
    except Exception:return False


class SyncPermission(BasePermission):
    def has_permission(self,request,view):
        u=request.user
        return bool(u and u.is_active and u.has_perm('diary_presets.sync_template') and u.has_perm('diary_presets.change_template'))


class Source(AuthView):
    permission_classes=[SyncPermission]
    parser_classes=[JSONParser]
    def handle_exception(self,exc):
        if isinstance(exc,SyncError):return Response({'code':exc.code,'message':exc.message,'retryable':exc.retryable},status=409)
        return super().handle_exception(exc)


class SyncOptions(AuthView):
    def get(self,request):
        allowed=SyncPermission().has_permission(request,self)
        enabled,reason=source_config()
        return Response(dict(environment=settings.MATERIAL_SYNC_ENVIRONMENT_ID or '未配置',target='生产环境',can_sync=allowed and settings.MATERIAL_SYNC_ENVIRONMENT_ID!='production',enabled=enabled,reason=reason))


class SourcePreflight(Source):
    @transaction.atomic
    def post(self,request,pk):
        enabled,reason=source_config()
        if not enabled:raise SyncError('SOURCE_DISABLED',reason)
        if not worker_ready():raise SyncError('WORKER_UNAVAILABLE','现有任务服务未就绪，请启动 Celery worker',True)
        lib=get_object_or_404(Template.objects.select_for_update().select_related('current'),pk=pk)
        if request.data.get('source_version')!=(lib.current.number if lib.current_id else 0) or request.data.get('expected_state_revision')!=lib.revision:raise SyncError('SOURCE_CHANGED','来源已更新，请刷新后重试')
        active=PresetSyncTask.objects.filter(side='source',library_uuid=pk,state__in=['preflighting','queued','checking','outcome_unknown','committed','verifying','committed_verification_pending']).order_by('-created_at').first()
        if active:return Response(task_json(active),status=202)
        if PresetSyncTask.objects.filter(side='source',actor=request.user,state__in=['preflighting','queued','checking','outcome_unknown']).count()>=3:raise SyncError('TOO_MANY_TASKS','最多同时处理三个同步任务')
        s=snapshot_for(lib)
        t=PresetSyncTask.objects.create(side='source',source_environment=settings.MATERIAL_SYNC_ENVIRONMENT_ID,library_uuid=pk,source_version=s['source_version'],content_hash=s['content_hash'],snapshot=s,actor=request.user,idempotency_key=uuid.uuid4().hex)
        transaction.on_commit(lambda:enqueue(t.pk))
        return Response(task_json(t),status=202)


class SourceTask(Source):
    def get(self,request,pk):
        t=get_object_or_404(PresetSyncTask,pk=pk,side='source')
        return Response(task_json(t))


class SourceConfirm(Source):
    @transaction.atomic
    def post(self,request,pk):
        t=get_object_or_404(PresetSyncTask.objects.select_for_update(),pk=pk,side='source')
        if t.state!='ready':return Response(task_json(t),status=202)
        if not t.expires_at or t.expires_at<timezone.now():raise SyncError('PREFLIGHT_EXPIRED','预检已过期，请重新检查')
        if request.data.get('preflight_token')!=t.baseline:raise SyncError('TARGET_CHANGED','预检确认信息不匹配')
        lib=Template.objects.select_for_update().select_related('current').get(pk=t.library_uuid)
        if snapshot_for(lib)!=t.snapshot:raise SyncError('SOURCE_CHANGED','来源发布内容已改变，请重新预检')
        if not worker_ready():raise SyncError('WORKER_UNAVAILABLE','现有任务服务未就绪',True)
        t.state='queued';t.actor=request.user;t.save()
        Event.objects.create(actor=request.user,template=lib,action='sync-confirm',detail={'task_id':str(t.pk),'hash':t.content_hash})
        transaction.on_commit(lambda:enqueue(t.pk))
        return Response(task_json(t),status=202)


class SourceRetry(Source):
    @transaction.atomic
    def post(self,request,pk):
        t=get_object_or_404(PresetSyncTask.objects.select_for_update(),pk=pk,side='source')
        if t.state in ('outcome_unknown','committed_verification_pending') or t.commit_status=='committed':
            t.result={**t.result,'network_failures':0,'manual_retry':False};t.save()
            transaction.on_commit(lambda:enqueue(t.pk))
            return Response(task_json(t),status=202)
        raise SyncError('NEW_PREFLIGHT_REQUIRED','请重新预检后同步；旧任务记录保留')


class SourceHistory(Source):
    def get(self,request,pk):
        from django.core.paginator import Paginator
        qs=PresetSyncTask.objects.filter(side='source',library_uuid=pk).order_by('-created_at')
        page=Paginator(qs,20).get_page(request.query_params.get('page',1))
        return Response({'items':[task_json(t) for t in page],'total':page.paginator.count})


class Receiver(APIView):
    authentication_classes=[]
    permission_classes=[]
    parser_classes=[JSONParser]
    def initial(self,request,*args,**kwargs):
        self.source=authorize(request)
        super().initial(request,*args,**kwargs)
    def handle_exception(self,exc):
        if isinstance(exc,SyncError):return Response({'code':exc.code,'message':exc.message,'retryable':exc.retryable},status=403 if exc.code=='AUTH_FAILED' else 409)
        return super().handle_exception(exc)


class Capabilities(Receiver):
    def get(self,request):
        return Response(dict(environment=settings.MATERIAL_SYNC_ENVIRONMENT_ID,schema_versions=[1],storage=wire_environment()))


class ReceivePreflight(Receiver):
    @transaction.atomic
    def post(self,request):
        s=request.data.get('snapshot')
        if request.data.get('storage')!=wire_environment():raise SyncError('OSS_ENV_MISMATCH','双方 OSS 配置不一致')
        validate_snapshot(s)
        if s['source_environment']!=self.source:raise SyncError('AUTH_FAILED','来源身份不匹配')
        key=request.data.get('request_key')
        if not isinstance(key,str) or not 1<=len(key)<=64:raise SyncError('INVALID_REQUEST','请求标识无效')
        # Separate target preflight/import idempotency namespaces, with environment bound.
        identity=digest([self.source,'preflight',key])
        old=PresetSyncTask.objects.filter(idempotency_key=identity).first()
        if old:
            if old.content_hash!=s['content_hash'] or old.snapshot!=s:raise SyncError('IDEMPOTENCY_CONFLICT','请求标识已用于其他内容')
            return Response(task_json(old),status=202)
        if not worker_ready():raise SyncError('WORKER_UNAVAILABLE','生产任务服务未就绪',True)
        if PresetSyncTask.objects.filter(side='target',state__in=['preflighting','queued','checking']).count()>=20:raise SyncError('TOO_MANY_TASKS','生产任务繁忙',True)
        t=PresetSyncTask.objects.create(side='target',source_environment=self.source,library_uuid=s['library_id'],source_version=s['source_version'],content_hash=s['content_hash'],snapshot=s,idempotency_key=identity)
        transaction.on_commit(lambda:enqueue(t.pk))
        return Response(task_json(t),status=202)


class ReceiveTask(Receiver):
    def get(self,request,pk):
        t=get_object_or_404(PresetSyncTask,pk=pk,side='target',source_environment=self.source)
        return Response(task_json(t))


class ReceiveImport(Receiver):
    @transaction.atomic
    def post(self,request):
        key=request.data.get('idempotency_key')
        if not isinstance(key,str) or not 1<=len(key)<=64:raise SyncError('INVALID_REQUEST','幂等标识无效')
        identity=digest([self.source,'import',key])
        old=PresetSyncTask.objects.filter(idempotency_key=identity).first()
        if old:
            if old.content_hash!=request.data.get('content_hash') or old.baseline!=request.data.get('target_fingerprint') or old.remote_preflight_id!=str(request.data.get('preflight_id')):raise SyncError('IDEMPOTENCY_CONFLICT','幂等键已用于其他请求')
            return Response(task_json(old),status=202)
        pre=get_object_or_404(PresetSyncTask,pk=serializers.UUIDField().run_validation(request.data.get('preflight_id')),side='target',source_environment=self.source,state='ready')
        if not pre.expires_at or pre.expires_at<timezone.now():raise SyncError('PREFLIGHT_EXPIRED','生产预检已过期')
        if pre.content_hash!=request.data.get('content_hash') or pre.baseline!=request.data.get('target_fingerprint'):raise SyncError('TARGET_CHANGED','预检内容不一致')
        PresetSyncSlot.objects.get_or_create(library_uuid=pre.library_uuid)
        slot=PresetSyncSlot.objects.select_for_update().get(pk=pre.library_uuid)
        old=PresetSyncTask.objects.filter(idempotency_key=identity).first()
        if old:
            if old.content_hash!=request.data.get('content_hash') or old.baseline!=request.data.get('target_fingerprint') or old.remote_preflight_id!=str(request.data.get('preflight_id')):raise SyncError('IDEMPOTENCY_CONFLICT','幂等键已用于其他请求')
            return Response(task_json(old),status=202)
        if slot.active_task_id:
            existing=slot.active_task
            if existing.state not in ('failed','conflict','succeeded','expired'):raise SyncError('TASK_IN_PROGRESS','该整本模板已有生产任务，请等待完成',True)
        t=PresetSyncTask.objects.create(side='target',source_environment=self.source,library_uuid=pre.library_uuid,source_version=pre.source_version,content_hash=pre.content_hash,snapshot=pre.snapshot,baseline=pre.baseline,state='queued',idempotency_key=identity,remote_preflight_id=str(pre.pk))
        slot.active_task=t;slot.save()
        transaction.on_commit(lambda:enqueue(t.pk))
        return Response(task_json(t),status=202)


class ReceiveByKey(Receiver):
    def get(self,request,key):
        t=PresetSyncTask.objects.filter(idempotency_key=digest([self.source,'import',key]),side='target',source_environment=self.source).first()
        return Response(dict(found=bool(t),**(task_json(t) if t else {})))
