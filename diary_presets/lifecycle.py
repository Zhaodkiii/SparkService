"""Template recycle bin and guarded deletion. Shared OSS objects are retained."""
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from .models import Template, Version, Upload, ResourceTask, Event, PresetImportEvent, PresetSyncTask, PresetSyncMapping, PresetSyncSlot, DownloadPlan
from .admin_support import Conflict

TERMINAL_UPLOADS = ['done','published','failed','cancelled','ready','conflict']
TERMINAL_SYNC = ['succeeded','failed','cancelled','expired','rejected']


def active_uploads(template):
    return Upload.objects.filter(template=template).exclude(status__in=TERMINAL_UPLOADS).exclude(status='uploading',created_at__lt=timezone.now()-timedelta(days=1))


def impact(template):
    from billing.models import ContentOffer, ContentOwnership, RedemptionOrder, RedemptionQuote
    from material_library.models import MaterialLibrary,TemplateMaterialLink
    versions=Version.objects.filter(template=template)
    offers=ContentOffer.objects.filter(target_kind='template',target_id=template.pk)
    ownerships=ContentOwnership.objects.filter(target_kind='template',target_id=template.pk)
    libraries=MaterialLibrary.objects.filter(template=template)
    links=TemplateMaterialLink.objects.filter(template=template,library__isnull=False)
    sync=PresetSyncTask.objects.filter(library_uuid=template.pk)
    counts=dict(versions=versions.count(),imports=PresetImportEvent.objects.filter(template=template).count(),
                ownerships=ownerships.count(),orders=RedemptionOrder.objects.filter(offer__in=offers).count(),
                quotes=RedemptionQuote.objects.filter(offer__in=offers).count(),
                pricing_versions=sum(o.policies.count() for o in offers),pricing_drafts=sum(ContentPolicyDraft.objects.filter(offer=o).count() for o in offers),
                material_libraries=libraries.count(),material_links=links.count(),
                active_uploads=active_uploads(template).count()+ResourceTask.objects.filter(upload__template=template,status__in=['queued','processing']).count(),uploads=Upload.objects.filter(template=template).count(),
                sync_records=sync.count(),active_sync=sync.exclude(state__in=TERMINAL_SYNC).count(),
                downloads=DownloadPlan.objects.filter(version__template=template).count())
    blockers=[]
    if template.current_id or counts['versions']:
        blockers.append('存在已发布版本：历史客户端使用无法仅凭统计排除，请保留模板及交付资源，可使用回收站停止新展示。')
    if counts['imports']: blockers.append('存在用户添加记录，不能永久删除。')
    if counts['ownerships'] or counts['orders'] or counts['quotes'] or counts['pricing_versions']:
        blockers.append('存在购买权益、订单、报价或已发布收费策略，需保留业务关联。')
    if counts['material_libraries'] or counts['material_links']:
        blockers.append('存在配套素材包或关联，请先在贴纸 / 背景管理中解除依赖；不会连带删除素材。')
    if counts['active_uploads']: blockers.append('有上传或资源处理任务尚未结束，请等待完成或先处理任务。')
    if counts['sync_records'] or PresetSyncMapping.objects.filter(target_version__template=template).exists():
        blockers.append('存在跨环境同步记录：当前操作不会删除生产副本，请保留同步追溯信息。')
    if counts['downloads']: blockers.append('存在下载交付记录，需要保留历史版本。')
    quick=not blockers and not template.draft.get('pages') and not template.draft.get('keys') and not counts['uploads']
    if not template.deleted_at and not quick:
        blockers.append('请先移入回收站，再执行永久删除；仅无资源的未发布空草稿可直接删除。')
    from billing.services import digest
    fingerprint=digest(dict(id=str(template.pk),revision=template.revision,deleted_at=template.deleted_at.isoformat() if template.deleted_at else None,counts=counts,draft=template.draft))
    return dict(id=str(template.pk),title=template.title,revision=template.revision,deleted_at=template.deleted_at,
                deletion_reason=template.deletion_reason,counts=counts,can_purge=not blockers,quick_delete=quick,
                can_trash=not counts['active_uploads'] and not counts['active_sync'],blockers=blockers,
                preview_hash=fingerprint,environment=getattr(settings,'MATERIAL_SYNC_ENVIRONMENT_ID','') or '当前环境',
                resource_note='只删除符合条件的当前环境模板及草稿元数据。共享 OSS 正式文件、临时上传文件及生产副本均保留，不会执行文件删除。')

# Import separately to keep the impact query definitions together.
from billing.models import ContentPolicyDraft


def audit(request,template,action,detail):
    from backoffice.models import AdminAuditLog
    AdminAuditLog.objects.create(user=request.user,action=action,resource_type='diary_template',resource_id=str(template.pk),
        method=request.method,path=request.path,status_code=200,
        request_payload={'reason':request.data.get('reason',''),'title':template.title},response_payload=detail)


class LifecycleInput(serializers.Serializer):
    revision=serializers.IntegerField(min_value=0)
    reason=serializers.CharField(max_length=500,allow_blank=False)
    title=serializers.CharField(required=False,allow_blank=True,max_length=120)
    expected_preview_hash=serializers.CharField(required=False)


def locked(request,pk):
    form=LifecycleInput(data=request.data);form.is_valid(raise_exception=True)
    obj=get_object_or_404(Template.objects.select_for_update(),pk=pk,audience='public')
    if form.validated_data['revision']!=obj.revision: raise Conflict('模板已变化，请重新加载删除影响')
    return obj,form.validated_data


class TemplateLifecycleMixin:
    def require_lifecycle_admin(self,request):
        if not request.user.is_superuser: raise PermissionDenied('模板回收站和永久删除仅限系统管理员')

    @action(detail=False,methods=['get'],url_path='recycle-bin')
    def recycle_bin(self,request):
        self.require_lifecycle_admin(request)
        class Query(serializers.Serializer):
            q=serializers.CharField(required=False,allow_blank=True,max_length=120,default='')
            page=serializers.IntegerField(min_value=1,default=1)
        form=Query(data=request.query_params);form.is_valid(raise_exception=True);d=form.validated_data
        qs=Template.objects.filter(audience='public',deleted_at__isnull=False).select_related('series','current').order_by('-deleted_at','id')
        if d['q']: qs=qs.filter(title__icontains=d['q'])
        total=qs.count();start=(d['page']-1)*20
        return Response(dict(items=[dict(id=str(t.pk),title=t.title,series_title=t.series.title,revision=t.revision,
                deleted_at=t.deleted_at,deletion_reason=t.deletion_reason,version=t.current.number if t.current_id else 0) for t in qs[start:start+20]],total=total,page=d['page']))

    @action(detail=True,methods=['get'],url_path='delete-preview')
    def delete_preview(self,request,pk=None):
        self.require_lifecycle_admin(request)
        return Response(impact(get_object_or_404(Template,pk=pk,audience='public')))

    @action(detail=True,methods=['post'],url_path='trash')
    @transaction.atomic
    def trash(self,request,pk=None):
        self.require_lifecycle_admin(request);obj,data=locked(request,pk)
        if obj.deleted_at: raise Conflict('模板已在回收站中')
        check=impact(obj)
        if not check['can_trash']: raise Conflict('有上传、资源处理或同步任务执行中，请完成后再移入回收站')
        # Keep published snapshots and their existing availability for historical
        # delivery. Discovery/purchases explicitly exclude deleted_at below.
        obj.deleted_at=timezone.now();obj.deletion_reason=data['reason'];obj.revision+=1;obj.save()
        Event.objects.create(template=obj,actor=request.user,action='trash',detail={'reason':data['reason']})
        audit(request,obj,'template_move_to_trash',{'title':obj.title,'revision':obj.revision})
        from .search import bump
        bump()
        return Response({'id':str(obj.pk),'revision':obj.revision,'deleted_at':obj.deleted_at})

    @action(detail=True,methods=['post'],url_path='restore-from-trash')
    @transaction.atomic
    def restore_from_trash(self,request,pk=None):
        self.require_lifecycle_admin(request);obj,data=locked(request,pk)
        if not obj.deleted_at: raise Conflict('模板不在回收站中')
        obj.deleted_at=None;obj.deletion_reason='';obj.active=False;obj.revision+=1;obj.save()
        Event.objects.create(template=obj,actor=request.user,action='restore_from_trash',detail={'reason':data['reason']})
        audit(request,obj,'template_restore_from_trash',{'title':obj.title,'revision':obj.revision,'active':False})
        from .search import bump
        bump()
        return Response({'id':str(obj.pk),'revision':obj.revision,'active':False})

    @action(detail=True,methods=['post'],url_path='permanent-delete')
    @transaction.atomic
    def permanent_delete(self,request,pk=None):
        self.require_lifecycle_admin(request);obj,data=locked(request,pk)
        from billing.models import ContentOffer
        list(ContentOffer.objects.select_for_update().filter(target_kind='template',target_id=obj.pk))
        check=impact(obj)
        if not check['can_purge']: raise Conflict('；'.join(check['blockers']))
        if data.get('title')!=obj.title: raise serializers.ValidationError('请输入完整模板名称确认永久删除')
        if data.get('expected_preview_hash')!=check['preview_hash']: raise Conflict('删除影响已变化，请重新检查')
        from billing.models import ContentOffer,ContentPolicyDraft
        from material_library.models import TemplateMaterialLink
        from billing.services import digest
        snapshot_id=str(obj.pk)
        audit(request,obj,'template_permanent_delete',{'title':obj.title,'counts':check['counts'],'draft_hash':digest(obj.draft),'resource_note':check['resource_note']})
        try:
            offers=ContentOffer.objects.select_for_update().filter(target_kind='template',target_id=obj.pk)
            ContentPolicyDraft.objects.filter(offer__in=offers).delete()
            offers.delete()
            TemplateMaterialLink.objects.filter(template=obj,library__isnull=True).delete()
            ResourceTask.objects.filter(upload__template=obj).delete()
            Upload.objects.filter(template=obj).delete()
            Event.objects.filter(template=obj).delete()
            PresetSyncSlot.objects.filter(library_uuid=obj.pk,active_task__isnull=True).delete()
            obj.delete()
        except ProtectedError:
            raise Conflict('模板新增了受保护的关联，整次删除已回滚，请重新检查')
        from .search import bump
        bump()
        return Response({'deleted':True,'id':snapshot_id,'resource_note':check['resource_note']})
