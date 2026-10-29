"""Authenticated pull queue. Only the independent processor reads resource bodies."""
import secrets
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework import serializers
from .models import FontUpload, FontAsset
from . import storage

class ProcessorPermission(BasePermission):
    def has_permission(self,request,view):
        expected=settings.FONT_PROCESSOR_TOKEN
        return bool(expected and secrets.compare_digest(request.headers.get('Authorization',''), 'Bearer '+expected))

class Processor(APIView):
    authentication_classes=[]
    permission_classes=[ProcessorPermission]
    @transaction.atomic
    def post(self,request):
        action=request.data.get('action')
        now=timezone.now()
        if action=='claim':
            job=FontUpload.objects.select_for_update().filter(Q(state='queued')|Q(state='processing',lease_until__lt=now)).order_by('updated_at').first()
            if not job:return Response({'job':None})
            job.state='processing';job.lease_token=uuid.uuid4();job.lease_until=now+timedelta(minutes=10);job.attempts+=1;job.save()
            return Response({'job':dict(id=str(job.pk),token=str(job.lease_token),url=storage.sign(job.candidate_key),etag=job.etag,kind=job.kind,sha256=job.declared_sha256,byte_size=job.byte_size,mime=job.mime)})
        job=FontUpload.objects.select_for_update().filter(pk=serializers.UUIDField().run_validation(request.data.get('id'))).first()
        if not job or job.state!='processing' or str(job.lease_token)!=request.data.get('token') or job.lease_until<=now:
            return Response({'detail':'处理任务租约失效'},status=409)
        if action=='heartbeat':
            job.lease_until=now+timedelta(minutes=10);job.save();return Response({'ok':True})
        if action=='fail':
            job.state='failed';job.error=str(request.data.get('error','验证失败'))[:300];job.save();return Response({'ok':True})
        if action!='complete':raise ValidationError('无效任务操作')
        actual=serializers.RegexField(r'^[a-f0-9]{64}$').run_validation(request.data.get('sha256'))
        if actual!=job.declared_sha256:raise ValidationError('字体实际摘要与上传声明不同')
        head=storage.verify(job.candidate_key,job.byte_size,job.mime,job.md5)
        if head.etag!=job.etag:raise ValidationError('候选对象发生变化')
        metadata=request.data.get('metadata',{})
        if not isinstance(metadata,dict):raise ValidationError('无效解析结果')
        if job.kind=='font':
            faces=metadata.get('faces',[])
            if len(faces)!=1 or not isinstance(faces[0].get('postscript_name'),str) or not faces[0]['postscript_name']:
                raise ValidationError('首版只开放已验证的单字面静态字体')
            if metadata.get('variable'):raise ValidationError('可变字体待专项验证，暂不可发布')
            # CoreText cannot safely distinguish equal PostScript names with different bytes.
            name=faces[0]['postscript_name']
            for other in FontAsset.objects.filter(kind='font').exclude(sha256=actual):
                if any(x.get('postscript_name')==name for x in other.metadata.get('faces',[])):
                    raise ValidationError('相同 PostScript 名称已有不同字体文件，需先解决版本注册冲突')
        if job.kind in ('cover','preview'):
            width=metadata.get('width',0);height=metadata.get('height',0)
            if not isinstance(width,int) or not isinstance(height,int) or width<1 or height<1 or width*height>24_000_000:raise ValidationError('图片尺寸无效')
            if job.kind=='cover' and (width!=height or width<512):raise ValidationError('封面须为至少 512 像素方图')
        asset=FontAsset.objects.create(family=job.family,kind=job.kind,object_key=job.candidate_key,sha256=actual,byte_size=job.byte_size,mime=job.mime,metadata=metadata)
        job.asset=asset;job.state='ready';job.error='';job.lease_token=None;job.lease_until=None;job.save()
        return Response({'asset_id':str(asset.pk)})
