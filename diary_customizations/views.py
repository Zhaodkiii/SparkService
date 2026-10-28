import re
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum, Q, Count
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView
from diary_presets.views import PresetAdmin, Conflict
from diary_presets.models import Series, Template
from .models import Request, Submission, Asset, Job, Delivery, Operation
from .workspace import annotated_requests, pending_query, facts, actions, next_step, reminder_available_at, TERMINAL
from .services import mutate, EDITABLE
from . import storage

BASE_CONFIG = dict(accepting=True,max_photos=30,max_photo_bytes=20*1024**2,max_total_bytes=300*1024**2,
                   max_active_requests=3,max_revision_rounds=2)

def cfg():
    return {**BASE_CONFIG, 'accepting':getattr(settings,'CUSTOMIZATIONS_ACCEPTING',True)}

def own(user,pk,admin=False,lock=False):
    qs=Request.objects.filter(deleted_at__isnull=True)
    if lock: qs=qs.select_for_update()
    if not admin: qs=qs.filter(owner=user)
    return get_object_or_404(qs,pk=pk)

def asset_json(a,include_urls=True):
    url=storage.sign(a.object_key) if include_urls and a.object_key else None
    return dict(id=str(a.pk),client_id=str(a.client_id),position=a.position,note=a.note,must_use=a.must_use,
                crop_allowed=a.crop_allowed,cover_preferred=a.cover_preferred,status=a.status,size=a.size,
                sha256=a.sha256,mime=a.mime,width=a.width,height=a.height,
                thumbnail_url=storage.sign(a.thumbnail_key) if include_urls and a.thumbnail_key else url,
                url=url,job_id=str(a.job.pk),error=a.job.error,available=bool(a.object_key and a.status=='ready'),
                removed=bool(a.deleted_at))

def delivery_json(d):
    snap=d.version.snapshot; manifest=snap['manifest']
    pages=snap['pages']
    cover=next((p for p in pages if p['data']['id']==manifest.get('coverPageID')),pages[0])
    def img(p,role):
        key=snap['keys'].get(p['data'].get('preview',{}).get(role,''))
        return storage.sign(key) if key else None
    return dict(id=str(d.pk),number=d.published_number or d.number,candidate_number=d.number,published_number=d.published_number,status=d.status,note=d.note,submission_id=d.submission_id,
        delivered_at=d.delivered_at,template_id=str(d.version.template_id),version=d.version.number,
        title=manifest['title'],page_count=len(pages),cover_url=img(cover,'thumbnailPath'),
        byte_size=sum(f['byteCount'] for f in manifest['files']),
        pages=[dict(id=p['data']['id'],title=p['data']['title'],preview_url=img(p,'largePath')) for p in pages],
        photo_slots=sum(s.get('kind')=='photo' for p in pages for s in p['data'].get('editableSlots',[])),
        text_slots=sum(s.get('kind')=='text' for p in pages for s in p['data'].get('editableSlots',[])))

def detail(obj,admin=False):
    submissions=list(obj.submissions.order_by('number'))
    all_assets={str(a.pk):a for a in obj.assets.select_related('job').order_by('position','created_at')}
    resolved=[]
    for sub in submissions:
        photos=[]
        for index,saved in enumerate(sub.snapshot.get('assets',[])):
            asset=all_assets.get(saved['id'])
            photo={**(asset_json(asset,False) if asset else {'available':False}),**saved,'position':saved.get('position',index)}
            photos.append(photo)
        resolved.append(dict(id=sub.pk,number=sub.number,snapshot=sub.snapshot,created_at=sub.created_at,resolved_assets=photos))
    value=dict(billing_quote_available=obj.billing_quotes.exists(),id=str(obj.pk),number='C'+obj.created_at.strftime('%Y%m%d')+'-'+obj.pk.hex[:8].upper(),
        title=obj.title,brief=obj.brief,status=obj.status,revision=obj.revision,created_at=obj.created_at,
        updated_at=obj.updated_at,due_at=obj.due_at,event_sequence=obj.event_sequence,
        last_read_sequence=obj.last_read_sequence,unread=obj.event_sequence>obj.last_read_sequence,
        revision_round=obj.revision_round,current_delivery_id=str(obj.current_delivery_id) if obj.current_delivery_id else None,
        assets=[asset_json(a,not admin) for a in all_assets.values() if not a.deleted_at],
        submissions=resolved,
        accepted_submission_id=obj.accepted_submission_id,latest_submission_id=submissions[-1].pk if submissions else None,
        pending_submission=facts(obj)['pending_submission'],allowed_actions=actions(obj,admin),next_step=next_step(obj),
        cancellation_requested=facts(obj)['cancellation_requested'],
        events=[dict(id=str(e.pk),sequence=e.sequence,action=e.action,message=e.message,details=e.details,created_at=e.created_at) for e in obj.events.all()],
        deliveries=[delivery_json(d) for d in obj.deliveries.select_related('version').order_by('-number') if admin or (d.status=='delivered' and d.version.template.active)])
    if admin:
        from notification_center.models import NotificationOutbox,NotificationIntent
        intents=NotificationIntent.objects.filter(business_reference_type="customization_request",business_id=str(obj.pk))
        from notification_center.models import ChannelDelivery
        value["notifications"]=[dict(id=i.pk,scene=i.business_scene,status=i.status,created_at=i.created_at,
            seen=obj.events.filter(pk=i.event_id,sequence__lte=obj.last_read_sequence).exists(),
            deliveries=list(ChannelDelivery.objects.filter(message__intent=i).order_by('pk').values('id','message_id','status','error_message','attempt_count','provider_status')),
            outbox=list(NotificationOutbox.objects.filter(idempotency_key=i.idempotency_key).values("status","last_error","available_at","attempts"))) for i in intents.order_by("-created_at")[:50]]
        value.update(owner_id=obj.owner_id,assigned_to=obj.assigned_to_id,internal_note=obj.internal_note,
                     owner_name=obj.owner.get_username(),assigned_name=obj.assigned_to.get_username() if obj.assigned_to else None,
                     cancellation_requested=facts(obj)['cancellation_requested'],overdue=facts(obj)['overdue'],
                     reminder_available_at=reminder_available_at(obj),
                     audit=[dict(id=o.pk,action=o.action,actor=o.actor.get_username(),created_at=o.created_at,details=o.details) for o in Operation.objects.filter(request=obj).exclude(action__in=['edit','submit','revision','confirm','delete']).select_related('actor').order_by('-created_at','-pk')[:100]],
                     jobs=list(obj.jobs.order_by('-created_at').values('id','kind','status','error','submission_id','created_at','result')))
    return value

class CustomizationThrottle(UserRateThrottle):
    rate="120/min"

class UserView(APIView):
    throttle_classes=[CustomizationThrottle]
    permission_classes=[IsAuthenticated]
    admin=False

class Config(UserView):
    def get(self,request): return Response(cfg())

class Requests(UserView):
    def get(self,request):
        qs=annotated_requests(Request.objects.filter(deleted_at__isnull=True).select_related('owner','assigned_to'))
        if not self.admin: qs=qs.filter(owner=request.user)
        summary={}
        if self.admin:
            search=request.query_params.get('q','').strip()[:100]
            if search:
                term=Q(title__icontains=search)|Q(owner__username__icontains=search)
                if search.isdigit(): term |= Q(owner_id=int(search))
                number=re.fullmatch(r'C?(\d{8})-([a-fA-F0-9]{8})',search,re.IGNORECASE)
                if number:
                    import datetime
                    try:
                        start=datetime.datetime.strptime(number[1],'%Y%m%d').replace(tzinfo=datetime.timezone.utc)
                        term |= Q(created_at__gte=start,created_at__lt=start+timedelta(days=1),id__startswith=number[2].lower())
                    except ValueError: pass
                try: term |= Q(pk=uuid.UUID(search))
                except ValueError: pass
                qs=qs.filter(term)
            if request.query_params.get('assigned_to'): qs=qs.filter(assigned_to_id=serializers.IntegerField(min_value=1).run_validation(request.query_params['assigned_to']))
            active=~Q(status__in=TERMINAL)
            buckets={'submitted':Q(status='submitted'),'pending_info':Q(status='in_production')&pending_query(),
                     'revision_requested':Q(status='revision_requested'),'ready_for_review':Q(has_candidate=True)&active&~pending_query(),
                     'cancellation':Q(cancellation_requested=True)&active,'overdue':Q(due_at__lt=timezone.now())&active}
            summary=qs.aggregate(**{k:Count('pk',filter=v) for k,v in buckets.items()})
            task=request.query_params.get('task')
            if task in buckets: qs=qs.filter(buckets[task])
        if request.query_params.get('status'): qs=qs.filter(status=request.query_params['status'])
        page=serializers.IntegerField(min_value=1,max_value=100000).run_validation(request.query_params.get('page',1))
        rows=list(qs[(page-1)*30:page*30+1])
        return Response(dict(results=[dict(id=str(o.pk),number='C'+o.created_at.strftime('%Y%m%d')+'-'+o.pk.hex[:8].upper(),title=o.title,status=o.status,revision=o.revision,
            unread=o.event_sequence>o.last_read_sequence,updated_at=o.updated_at,owner_id=o.owner_id if self.admin else None,
            owner_name=o.owner.get_username() if self.admin else None,assigned_to=o.assigned_to_id if self.admin else None,
            assigned_name=o.assigned_to.get_username() if self.admin and o.assigned_to else None,due_at=o.due_at,
            **facts(o)) for o in rows[:30]],next_page=page+1 if len(rows)>30 else None,summary=summary))
    @transaction.atomic
    def post(self,request):
        if not cfg()['accepting']: raise Conflict('暂时停止受理，请稍后再试')
        key=serializers.UUIDField().run_validation(request.data.get('creation_key'))
        # Stable parent lock also serializes quota reservations for a first request.
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        obj=Request.objects.filter(owner=request.user,creation_key=key).first()
        if obj: return Response(detail(obj))
        if Request.objects.filter(owner=request.user,deleted_at__isnull=True).exclude(status__in=['completed','cancelled','rejected']).count()>=3:
            raise Conflict('最多同时进行 3 个定制需求')
        obj=Request.objects.create(owner=request.user,creation_key=key)
        return Response(detail(obj),status=201)

class RequestDetail(UserView):
    def get(self,request,pk): return Response(detail(own(request.user,pk,self.admin),self.admin))
    def patch(self,request,pk): return self.perform(request,pk,'edit')
    def perform(self,request,pk,action):
        own(request.user,pk,self.admin)
        obj=mutate(pk,request.user,action,request.data,request.headers.get('Idempotency-Key',''),self.admin)
        if obj.deleted_at: return Response({'deleted':True})
        return Response(detail(obj,self.admin))

class Action(RequestDetail):
    def post(self,request,pk,action): return self.perform(request,pk,action)

class Read(UserView):
    @transaction.atomic
    def post(self,request,pk):
        obj=own(request.user,pk,lock=True)
        sequence=serializers.IntegerField(min_value=0,max_value=obj.event_sequence).run_validation(request.data.get('sequence'))
        obj.last_read_sequence=max(obj.last_read_sequence,sequence)
        obj.save(update_fields=['last_read_sequence'])
        return Response({'last_read_sequence':obj.last_read_sequence})

class Summary(UserView):
    def get(self,request):
        qs=Request.objects.filter(owner=request.user,deleted_at__isnull=True,event_sequence__gt=F('last_read_sequence'))
        return Response({'unread_request_count':qs.count()})

class AssetURLs(UserView):
    def post(self,request,pk):
        obj=own(request.user,pk,self.admin)
        ids=serializers.ListField(child=serializers.UUIDField(),max_length=30).run_validation(request.data.get('asset_ids',[]))
        permitted=obj.assets.all()
        if request.data.get('submission_id') is not None:
            sub=get_object_or_404(obj.submissions,pk=request.data['submission_id'])
            permitted=permitted.filter(pk__in=[a['id'] for a in sub.snapshot.get('assets',[])])
        else: permitted=permitted.filter(deleted_at__isnull=True)
        assets=list(permitted.filter(pk__in=ids,status='ready').exclude(object_key='').select_related('job'))
        if len(assets)!=len(set(ids)): raise ValidationError('部分照片已过期或不属于当前资料版本，请刷新后重试')
        return Response({'assets':[asset_json(a) for a in assets],'expires_at':timezone.now()+timedelta(minutes=10)})

class Operators(UserView):
    permission_classes=[PresetAdmin]
    def get(self,request):
        users=get_user_model().objects.filter(is_active=True).filter(Q(is_superuser=True)|Q(user_permissions__codename='change_template',user_permissions__content_type__app_label='diary_presets')|Q(groups__permissions__codename='change_template',groups__permissions__content_type__app_label='diary_presets')).distinct()
        return Response({'results':[dict(id=u.pk,name=u.get_username()) for u in users.order_by('pk')]})

class OperationStatus(UserView):
    permission_classes=[PresetAdmin];admin=True
    def get(self,request,pk):
        obj=own(request.user,pk,True)
        operation=Operation.objects.filter(request=obj,actor=request.user,key=request.query_params.get('key','')).first()
        return Response(dict(applied=bool(operation),action=operation.action if operation else None,
                             revision=operation.details.get('revision') if operation else None))

class Assets(UserView):
    @transaction.atomic
    def post(self,request,pk):
        obj=own(request.user,pk,lock=True)
        if obj.status not in EDITABLE: raise Conflict('当前不能上传照片')
        client_id=serializers.UUIDField().run_validation(request.data.get('client_id'))
        size=serializers.IntegerField(min_value=1,max_value=20*1024**2).run_validation(request.data.get('size'))
        sha=request.data.get('sha256',''); mime=request.data.get('mime')
        if not re.fullmatch('[0-9a-f]{64}',sha) or mime not in ('image/jpeg','image/png'): raise ValidationError('照片信息不合法')
        old=obj.assets.filter(client_id=client_id).first()
        if old:
            if old.deleted_at or old.job.sha256!=sha or old.job.size!=size: raise Conflict('照片会话不匹配')
            return Response(storage.upload(old.job))
        qs=obj.assets.filter(deleted_at__isnull=True)
        if qs.count()>=30 or (qs.aggregate(v=Sum('size'))['v'] or 0)+size>300*1024**2: raise ValidationError('超过照片数量或总大小限制')
        width=serializers.IntegerField(min_value=0,max_value=4096).run_validation(request.data.get('width',0))
        height=serializers.IntegerField(min_value=0,max_value=4096).run_validation(request.data.get('height',0))
        asset=Asset.objects.create(request=obj,client_id=client_id,size=size,sha256=sha,mime=mime,position=qs.count(),width=width,height=height)
        jid=uuid.uuid4()
        job=Job.objects.create(id=jid,request=obj,actor=request.user,asset=asset,kind='asset',size=size,sha256=sha,
                               object_key=storage.scope(obj)+f'inputs/{jid}/photo.'+('png' if mime=='image/png' else 'jpg'))
        return Response(storage.upload(job),status=201)

class AssetDetail(UserView):
    @transaction.atomic
    def patch(self,request,pk,asset):
        obj=own(request.user,pk,lock=True)
        if obj.status not in EDITABLE: raise Conflict('资料已提交，请等待补充阶段')
        a=get_object_or_404(obj.assets,pk=asset,deleted_at__isnull=True)
        for field in ('must_use','crop_allowed','cover_preferred'):
            if field in request.data: setattr(a,field,serializers.BooleanField().run_validation(request.data[field]))
        if 'note' in request.data: a.note=serializers.CharField(max_length=500,allow_blank=True).run_validation(request.data['note'])
        if 'position' in request.data: a.position=serializers.IntegerField(min_value=0,max_value=29).run_validation(request.data['position'])
        a.save(); obj.revision+=1; obj.save()
        return Response(detail(obj))
    @transaction.atomic
    def delete(self,request,pk,asset):
        obj=own(request.user,pk,lock=True)
        if obj.status not in EDITABLE: raise Conflict('资料已提交')
        a=get_object_or_404(obj.assets,pk=asset,deleted_at__isnull=True)
        a.deleted_at=timezone.now(); a.save(); obj.revision+=1; obj.save()
        return Response(detail(obj))

class Upload(UserView):
    def get_job(self,request,pk,lock=False):
        qs=Job.objects.select_for_update() if lock else Job.objects.all()
        if not self.admin: qs=qs.filter(request__owner=request.user,kind='asset')
        return get_object_or_404(qs,pk=pk,request__deleted_at__isnull=True)
    def get(self,request,pk):
        j=self.get_job(request,pk)
        return Response(dict(id=str(j.pk),status=j.status,error=j.error))
    @transaction.atomic
    def post(self,request,pk,action):
        j=self.get_job(request,pk,True)
        obj=own(request.user,j.request_id,self.admin,True)
        if j.kind=='asset' and (obj.status not in EDITABLE or j.asset.deleted_at): raise Conflict('上传不可用')
        if j.kind=='delivery' and obj.status not in ('in_production','revision_requested','delivered'): raise Conflict('制作已结束')
        if j.kind=='delivery' and (j.submission_id!=obj.accepted_submission_id or facts(obj)['pending_submission']): raise Conflict('制作依据已变化，请先确认最新资料后重新上传候选')
        if j.kind=='asset' and action in ('complete','retry'):
            if action=='retry' and j.status!='failed': raise Conflict('当前不能重试')
            if j.status=='abandoned': raise Conflict('上传会话已结束，请重新添加照片')
            if j.status=='uploading' and timezone.now()-j.created_at>timedelta(days=1): raise Conflict('上传会话已过期')
            # The client acknowledges a successful OSS PUT. No OSS request, decoding,
            # hashing, copying or processor task is performed by the API host.
            a=j.asset
            if a.status!='ready':
                a.object_key=j.object_key
                a.status='ready'
                a.save(update_fields=['object_key','status'])
            j.status='ready';j.error='';j.lease=None;j.lease_until=None
            j.result={'object_key':a.object_key,'completion':'client_acknowledged'}
            j.save(update_fields=['status','error','lease','lease_until','result'])
            return Response(dict(id=str(j.pk),status='ready'))
        if action=='refresh':
            if j.status!='uploading' or timezone.now()-j.created_at>timedelta(days=1): raise Conflict('上传会话已结束')
            return Response(storage.upload(j))
        if action=='retry':
            if j.status!='failed': raise Conflict('当前不能重试')
            j.status='queued';j.error='';j.save()
            from diary_presets.resource_queue import enqueue
            enqueue(j)
        elif action=='complete':
            if j.status=='uploading':
                if timezone.now()-j.created_at>timedelta(days=1): raise Conflict('上传会话已过期')
                from diary_presets.storage import bucket
                if bucket().head_object(j.object_key).content_length!=j.size: raise ValidationError('上传大小不符')
                j.status='queued';j.save()
                from diary_presets.resource_queue import enqueue
                enqueue(j)
        else: raise ValidationError('未知上传操作')
        return Response(dict(id=str(j.pk),status=j.status),status=202)

class DeliveryUploads(UserView):
    permission_classes=[PresetAdmin];admin=True
    @transaction.atomic
    def post(self,request,pk):
        obj=own(request.user,pk,True,True)
        if obj.status not in ('in_production','revision_requested','delivered') or not obj.accepted_submission_id: raise Conflict('请先受理并固定制作依据')
        if facts(obj)['pending_submission']: raise Conflict('用户已补充资料，请先确认最新制作依据')
        if request.data.get('submission_id') is not None and request.data['submission_id']!=obj.accepted_submission_id: raise Conflict('上传绑定的制作依据已变化')
        size=serializers.IntegerField(min_value=1,max_value=1024**3).run_validation(request.data.get('size'))
        sha=request.data.get('sha256','')
        if not re.fullmatch('[0-9a-f]{64}',sha): raise ValidationError('缺少有效源包摘要')
        old=Job.objects.filter(request=obj,kind='delivery',sha256=sha,submission=obj.accepted_submission).first()
        if old: return Response(storage.upload(old) if old.status=='uploading' else dict(id=str(old.pk),status=old.status))
        series,_=Series.objects.get_or_create(slug='private-custom',defaults={'title':'专属定制','active':False})
        Template.objects.get_or_create(customization_id=obj.pk,defaults={'series':series,'title':obj.title,'audience':'private','owner':obj.owner})
        jid=uuid.uuid4()
        j=Job.objects.create(id=jid,request=obj,actor=request.user,submission=obj.accepted_submission,kind='delivery',size=size,sha256=sha,
            object_key=storage.scope(obj)+f'delivery-staging/{jid}/source.zip')
        return Response(storage.upload(j),status=201)

class Export(UserView):
    permission_classes=[PresetAdmin];admin=True
    def post(self,request,pk):
        obj=own(request.user,pk,True)
        sub=get_object_or_404(obj.submissions,pk=request.data.get('submission_id',obj.accepted_submission_id))
        ids=[a['id'] for a in sub.snapshot['assets']]
        assets={str(a.pk):a for a in obj.assets.filter(pk__in=ids,status='ready').exclude(object_key='')}
        if len(assets)!=len(ids): raise ValidationError('本提交有照片已过期或不可下载，请核对资料后再导出')
        return Response(dict(request_id=str(obj.pk),submission_id=sub.pk,snapshot=sub.snapshot,
            assets=[dict(id=str(assets[k].pk),sha256=assets[k].sha256,mime=assets[k].mime,size=assets[k].size,url=storage.sign(assets[k].object_key)) for k in ids]))

class Preference(UserView):
    def get(self,request):
        from notification_center.models import NotificationPreference
        p=NotificationPreference.objects.filter(user=request.user,topic_key='diary.customization',channel='apns').first()
        return Response(dict(enabled=p.enabled if p else True,quiet_hours=p.quiet_hours if p else {}))
    def patch(self,request):
        from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
        from notification_center.models import NotificationPreference
        enabled=serializers.BooleanField().run_validation(request.data.get('enabled'))
        old=NotificationPreference.objects.filter(user=request.user,topic_key='diary.customization',channel='apns').first()
        quiet=request.data.get('quiet_hours',old.quiet_hours if old else {})
        if not isinstance(quiet,dict): raise ValidationError('静默设置不合法')
        if quiet:
            if not all(re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',str(quiet.get(k,''))) for k in ('start','end')): raise ValidationError('静默时间不合法')
            try: ZoneInfo(quiet.get('timezone',''))
            except (ZoneInfoNotFoundError,ValueError,TypeError): raise ValidationError('时区不合法')
        NotificationPreference.objects.update_or_create(user=request.user,topic_key='diary.customization',channel='apns',defaults={'enabled':enabled,'quiet_hours':quiet})
        return self.get(request)
