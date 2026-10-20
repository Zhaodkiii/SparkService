import hashlib
import json
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError
from rest_framework import serializers
from diary_presets.views import Conflict
from .models import Request, Submission, Asset, Job, Delivery, Event, Operation

EDITABLE = ('draft','needs_info')
TERMINAL = ('completed','cancelled','rejected')
BRIEF_FIELDS = {'description':3000,'category':60,'style':200,'important_text':2000,'avoid':500,'story_order':1000,'page_preference':200}

def checked_brief(data):
    if not isinstance(data,dict): raise ValidationError('需求描述格式不合法')
    result = {}
    for key, limit in BRIEF_FIELDS.items():
        value = data.get(key, '')
        if not isinstance(value,str) or len(value)>limit: raise ValidationError(f'{key} 长度不符合要求')
        result[key] = value.strip()
    return result

def emit(obj, action, actor, message='', details=None, notify=False):
    obj.event_sequence += 1
    event = Event.objects.create(request=obj,sequence=obj.event_sequence,action=action,actor=actor,
                                 message=message,details=details or {})
    obj.save()
    if notify:
        from .notifications import enqueue
        enqueue(event)
    return event

@transaction.atomic
def mutate(pk, actor, action, data, key, admin=False):
    requested_action = action
    obj = get_object_or_404(Request.objects.select_for_update(),pk=pk,deleted_at__isnull=True)
    if not admin and obj.owner_id != actor.pk: raise ValidationError('需求不可用')
    if not key or len(key)>100: raise ValidationError('请提供 Idempotency-Key')
    digest = hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    old = Operation.objects.filter(request=obj,actor=actor,key=key).first()
    if old:
        if old.digest != digest or old.action != action: raise Conflict('幂等键已用于其他操作')
        return obj
    if data.get('expected_revision') != obj.revision: raise Conflict('资料已被其他操作更新；已保留你的输入，请先刷新并对比最新内容')
    message = data.get('message','')
    if not isinstance(message,str) or len(message)>3000: raise ValidationError('说明最多 3000 字')
    details = {}
    notify = False
    if action == 'edit' and not admin:
        if obj.status not in EDITABLE: raise Conflict('当前阶段不能修改资料')
        title = data.get('title',obj.title)
        if not isinstance(title,str) or len(title)>60: raise ValidationError('主题最多 60 字')
        obj.title = title.strip()
        if 'brief' in data: obj.brief = checked_brief(data['brief'])
    elif action == 'submit' and not admin:
        if obj.status not in EDITABLE: raise Conflict('当前阶段不能提交')
        assets = list(obj.assets.filter(deleted_at__isnull=True).order_by('position','created_at'))
        if not obj.title or not obj.brief.get('description') or not 1<=len(assets)<=30 or any(a.status!='ready' for a in assets):
            raise ValidationError('请填写主题、描述，并等待全部照片上传完成')
        snapshot = {'title':obj.title,'brief':obj.brief,'assets':[dict(id=str(a.pk),position=a.position,note=a.note,
                    must_use=a.must_use,crop_allowed=a.crop_allowed,cover_preferred=a.cover_preferred,sha256=a.sha256,
                    size=a.size,mime=a.mime,width=a.width,height=a.height) for a in assets]}
        number = obj.submissions.count()+1
        sub = Submission.objects.create(request=obj,number=number,snapshot=snapshot)
        details={'submission_id':sub.pk,'submission_number':number}
        obj.status = obj.resume_status if obj.status=='needs_info' else 'submitted'
        action = 'info_submitted' if number>1 else 'submitted'
    elif action == 'cancel' and not admin:
        if obj.status in ('draft','submitted','needs_info'):
            obj.status = 'cancelled'
        elif obj.status in ('in_production','revision_requested'):
            action = 'cancellation_requested'
            if obj.events.filter(action=action).exists(): raise Conflict('已申请取消，请等待处理')
        else: raise Conflict('当前状态不能撤回')
    elif action == 'revision' and not admin:
        if obj.status!='delivered' or str(obj.current_delivery_id)!=data.get('delivery_id'): raise Conflict('交付版本已变化')
        if obj.revision_round>=2 or not message.strip(): raise ValidationError('请填写修改意见；最多支持两轮修改')
        obj.revision_round += 1
        obj.status='revision_requested'
        details={'base_delivery_id':str(obj.current_delivery_id),'round':obj.revision_round}
        action='revision_requested'
    elif action == 'confirm' and not admin:
        if obj.status!='delivered' or str(obj.current_delivery_id)!=data.get('delivery_id'): raise Conflict('请确认当前交付版本')
        obj.status='completed'; action='completed'
    elif action == 'delete' and not admin:
        obj.deleted_at=timezone.now(); action='deletion_requested'
        obj.deliveries.filter(status='delivered').update(status='withdrawn')
    elif admin:
        if action=='accept':
            latest=obj.submissions.order_by('-number').first()
            if obj.status not in ('submitted','revision_requested','in_production'): raise Conflict('当前状态不能受理')
            selected=serializers.IntegerField(min_value=1).run_validation(data.get('submission_id'))
            sub = obj.submissions.filter(pk=selected).first()
            if not sub: raise ValidationError('请选择制作依据')
            if not latest or sub.pk!=latest.pk: raise Conflict('请选择最新提交；历史资料仅供对照和下载')
            if obj.status=='in_production' and obj.accepted_submission_id==sub.pk: raise Conflict('该提交已经是当前制作依据')
            was_producing=obj.status=='in_production'
            obj.accepted_submission=sub; obj.assigned_to=actor; obj.status='in_production'
            obj.jobs.filter(kind='delivery',status__in=['uploading','queued','processing']).exclude(submission=sub).update(status='abandoned',error='制作依据已更新，请重新制作并上传',lease=None,lease_until=None)
            action='basis_updated' if was_producing else ('revision_started' if obj.revision_round else 'accepted')
            details={'submission_id':sub.pk,'submission_number':sub.number}
        elif action=='assign':
            if obj.status in TERMINAL: raise Conflict('需求已结束')
            from django.contrib.auth import get_user_model
            selected=serializers.IntegerField(min_value=1).run_validation(data.get('assigned_to'))
            assignee=get_user_model().objects.filter(pk=selected,is_active=True).first()
            if not assignee or not (assignee.is_superuser or assignee.has_perm('diary_presets.change_template')): raise ValidationError('请选择有制作权限的管理员')
            details={'previous_assigned_to':obj.assigned_to_id,'assigned_to':assignee.pk}
            obj.assigned_to=assignee
            action='assignment_updated'
        elif action=='request-info':
            if obj.status not in ('submitted','in_production'): raise Conflict('当前状态不能要求补充')
            if not message.strip(): raise ValidationError('请填写需要补充的内容')
            obj.resume_status=obj.status; obj.status='needs_info'; action='info_requested'; notify=True
        elif action in ('reject','cancel'):
            if obj.status in TERMINAL: raise Conflict('需求已结束')
            if not message.strip(): raise ValidationError('请填写原因')
            obj.status='rejected' if action=='reject' else 'cancelled'; action=obj.status; notify=True
        elif action=='remind':
            if obj.status not in ('needs_info','delivered'): raise Conflict('当前没有可提醒的待办')
            if obj.events.filter(action='pending_reminder',created_at__gt=timezone.now()-timedelta(hours=1)).exists(): raise Conflict('一小时内已提醒，请勿重复发送')
            details={'delivery_id':str(obj.current_delivery_id) if obj.current_delivery_id else None}
            action='pending_reminder'; notify=True
        elif action=='production':
            if obj.status in TERMINAL: raise Conflict('需求已结束')
            obj.internal_note=str(data.get('internal_note',obj.internal_note))[:5000]
            if 'due_at' in data:
                value=data['due_at']; due=parse_datetime(value) if value else None
                if value and (due is None or timezone.is_naive(due)): raise ValidationError('日期必须包含时区')
                if due!=obj.due_at:
                    notify=bool(obj.due_at); obj.due_at=due; action='due_changed'
            if action=='production': action='production_updated'
            details={'due_at':obj.due_at.isoformat() if obj.due_at else None}
        elif action=='deliver':
            if obj.status not in ('in_production','revision_requested','delivered'): raise Conflict('当前阶段不能交付')
            latest=obj.submissions.order_by('-number').values_list('pk',flat=True).first()
            if latest!=obj.accepted_submission_id: raise Conflict('用户已补充资料，请先确认最新制作依据')
            delivery=obj.deliveries.select_for_update().filter(pk=data.get('delivery_id'),status='ready_for_review').first()
            if not delivery or delivery.submission_id!=obj.accepted_submission_id: raise Conflict('候选或制作依据已失效')
            used=data.get('used_asset_ids',[])
            if not isinstance(used,list) or any(not isinstance(x,str) for x in used) or len(used)!=len(set(used)): raise ValidationError('照片映射无效')
            all_ids={a['id'] for a in delivery.submission.snapshot['assets']}
            must={a['id'] for a in delivery.submission.snapshot['assets'] if a.get('must_use')}
            if not set(used)<=all_ids or not must<=set(used): raise ValidationError('请核对必用照片和来源映射')
            if data.get('ios_reviewed') is not True: raise ValidationError('请先完成 iOS 视觉与编辑验收')
            last_number=obj.deliveries.aggregate(n=Max('published_number'))['n'] or 0
            delivery.published_number=last_number+1
            delivery.production_map={'used_asset_ids':used,'ios_reviewed':True}
            delivery.note=message; delivery.status='delivered'; delivery.delivered_by=actor; delivery.delivered_at=timezone.now(); delivery.save()
            action='redelivered' if last_number else 'delivered'
            obj.current_delivery=delivery; obj.status='delivered'; notify=True
            details={'delivery_id':str(delivery.pk)}
        elif action in ('withdraw','rollback'):
            if obj.status in TERMINAL: raise Conflict('需求已结束，不能调整交付')
            delivery=obj.deliveries.select_for_update().filter(pk=data.get('delivery_id'),status='delivered').first()
            if not delivery or not message.strip(): raise ValidationError('请选择有效交付并填写原因')
            if action=='withdraw':
                delivery.status='withdrawn'; delivery.save(update_fields=['status'])
                if obj.current_delivery_id==delivery.pk: obj.current_delivery=None; obj.status='in_production'
                action='delivery_withdrawn'
            else:
                if obj.current_delivery_id==delivery.pk: raise Conflict('已是当前版本')
                obj.current_delivery=delivery; obj.status='delivered'; action='delivery_rolled_back'
            details={'delivery_id':str(delivery.pk)}; notify=True
        else: raise ValidationError('未知操作')
    else: raise ValidationError('未知操作')
    obj.revision+=1
    if action not in ('edit','production_updated','assignment_updated'):
        emit(obj,action,actor,message,details,notify)
    else: obj.save()
    Operation.objects.create(request=obj,actor=actor,key=key,action=requested_action,digest=digest,
                             details={**details,'message':message,'revision':obj.revision})
    return obj
