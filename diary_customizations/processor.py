import uuid
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from diary_presets.views import ProcessorPermission, Conflict
from diary_presets.models import Template, Version
from .models import Job, Request, Delivery
from .storage import scope

class Processor(APIView):
    authentication_classes=[]
    permission_classes=[ProcessorPermission]
    @transaction.atomic
    def post(self,request):
        now=timezone.now()
        if request.data.get('action')=='claim':
            return Response({'detail':'请使用统一手帐资源处理队列'},status=410)
        j=get_object_or_404(Job.objects.select_for_update(),pk=request.data.get('id'))
        obj=Request.objects.select_for_update().get(pk=j.request_id)
        if j.status!='processing' or str(j.lease)!=request.data.get('lease') or not j.lease_until or j.lease_until<now:
            raise Conflict('处理租约已过期')
        if obj.deleted_at or obj.status in ('cancelled','rejected') or (j.asset_id and j.asset.deleted_at):
            j.status='abandoned';j.save();return Response({'status':j.status})
        if j.kind!='delivery': raise Conflict('照片直传完成后直接登记，不再接受照片处理回调')
        if request.data.get('error'):
            j.status='failed';j.error=str(request.data['error'])[:1000];j.save()
            return Response({'status':j.status})
        result=request.data.get('result')
        if not isinstance(result,dict): raise ValidationError('缺少处理结果')
        prefix=scope(obj)
        if j.kind=='delivery':
            if not result.get('pages') or len(result['pages'])>100 or not result.get('keys') or any(not k.startswith(prefix+'blobs/') for k in result['keys'].values()):
                raise ValidationError('非法定制资源包')
            if obj.accepted_submission_id!=j.submission_id: raise Conflict('制作依据已变化，请重新上传')
            t=Template.objects.select_for_update().get(customization_id=obj.pk,audience='private',owner=obj.owner)
            manifest=result['manifest']
            source_number=manifest.get('packageVersion',0)
            previous=[x.get('source_package_version',0) for x in obj.jobs.filter(kind='delivery',status='ready').exclude(pk=j.pk).values_list('result',flat=True)]
            if previous and source_number<=max(previous):
                j.status='failed';j.error='内容变化必须提高源包 packageVersion 后重新上传';j.save()
                return Response({'status':j.status})
            number=(t.versions.order_by('-number').values_list('number',flat=True).first() or 0)+1
            manifest.update(templateBookID=str(t.pk),packageVersion=number,title=obj.title)
            v=Version.objects.create(template=t,number=number,snapshot=result,actor=j.actor)
            t.current=v;t.draft=result;t.revision+=1;t.save()
            d=Delivery.objects.create(request=obj,submission=j.submission,job=j,version=v,number=obj.deliveries.count()+1)
            result={'delivery_id':str(d.pk),'version':number,'source_package_version':source_number}
        j.result=result;j.status='ready';j.error='';j.save()
        return Response(dict(id=str(j.pk),status=j.status))
