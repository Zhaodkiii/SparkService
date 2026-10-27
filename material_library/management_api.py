"""Administrative metadata API. Deliberately accepts JSON only, never file bodies."""
import hashlib
import json
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q, F, Max, Count, OuterRef, Subquery
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.exceptions import ValidationError
from diary_presets.storage import prefix
from rest_framework.permissions import BasePermission

class MaterialAdminPermission(BasePermission):
    def has_permission(self,request,view):
        user=request.user
        if not user or not user.is_active: return False
        if user.is_superuser or user.has_perm("diary_presets.change_template"): return True
        action = "view_materiallibrary" if request.method == "GET" else "change_materiallibrary"
        if view.__class__.__name__ in ("Publish", "Validate"): action = "publish_materiallibrary"
        if view.__class__.__name__ in ("Availability","MaterialAvailability"): action = "takedown_materiallibrary"
        return user.has_perm("material_library."+action)
from .views import AuthView, item_json
from .catalog_v2 import Conflict, blob_json, public_libraries
from .models import *
from .services import revision
from .direct_uploads import upload_status, metadata, upload_plan, confirm_upload


class Admin(AuthView):
    permission_classes=[MaterialAdminPermission]
    parser_classes=[JSONParser]
    def initial(self,request,*args,**kwargs):
        super().initial(request,*args,**kwargs)
        if request.method in ('POST','PATCH','PUT') and request.content_type != 'application/json':
            from rest_framework.exceptions import UnsupportedMediaType
            raise UnsupportedMediaType(request.content_type)


def audit(request, lib, action, detail):
    MaterialAudit.objects.create(actor=request.user,library=lib,action=action,detail=detail)


def draft_content(lib):
    content=dict(lib.current.content) if lib.current_id else {}
    content.setdefault('title',lib.title); content.setdefault('description','')
    content.setdefault('tags',[]); content.setdefault('cover',None); content.setdefault('previews',[])
    content['items']=[{'revision':i.revision_id} for i in lib.current.items.all()] if lib.current_id else []
    return content


def clean_text(value,maximum,required=False):
    if not isinstance(value,str) or len(value.strip())>maximum or (required and not value.strip()): raise ValidationError('文本长度不正确')
    return value.strip()


def clean_content(content,lib,strict=False):
    if not isinstance(content,dict): raise ValidationError('草稿必须为对象')
    result={k:content.get(k) for k in ('title','description','tags','cover','previews','items')}
    result['title']=clean_text(result['title'],60,True)
    result['description']=clean_text(result['description'] or '',1000)
    tags=result['tags'] or []
    if not isinstance(tags,list) or len(tags)>20: raise ValidationError('标签最多 20 项')
    result['tags']=list(dict.fromkeys(clean_text(t,30,True) for t in tags))
    previews=result['previews'] or []
    if not isinstance(previews,list) or len(previews)>8: raise ValidationError('展示图最多 8 张')
    result['previews']=previews
    refs=previews+([result['cover']] if result['cover'] else [])
    if any(not isinstance(k,str) or len(k)!=64 for k in refs): raise ValidationError('图片资源无效')
    if ResourceBlob.objects.filter(pk__in=refs).count()!=len(set(refs)): raise ValidationError('图片尚未通过验证')
    if ResourceBlob.objects.filter(pk__in=refs).exclude(object_key__startswith=prefix()+'blobs/').exists(): raise ValidationError('私人资源不能加入公共素材包')
    if result['cover']:
        cover=ResourceBlob.objects.get(pk=result['cover'])
        if min(cover.width,cover.height)<512 or cover.width!=cover.height: raise ValidationError('封面须为至少 512×512 的方图')
    if any(b.width<750 for b in ResourceBlob.objects.filter(pk__in=previews)): raise ValidationError('展示图宽度至少 750 像素')
    items=result['items'] or []
    if not isinstance(items,list) or len(items)>500: raise ValidationError('每包最多 500 张')
    ids=[]; materials=set()
    for item in items:
        if not isinstance(item,dict): raise ValidationError('无效素材条目')
        r=get_object_or_404(MaterialRevision,pk=serializers.IntegerField(min_value=1).run_validation(item.get('revision')))
        if r.material_id in materials: raise ValidationError('同一素材不可重复加入')
        if r.material.material_type!=lib.library_type or not r.material.active: raise ValidationError('素材类型不符或已下架')
        if not r.resource.object_key.startswith(prefix()+'blobs/') or not r.thumbnail.object_key.startswith(prefix()+'blobs/'):raise ValidationError('资源不属于公共素材目录')

        if strict:
            from .catalog import validate_category
            try: validate_category(r.kind,r.subcategory,lib.library_type)
            except ValueError as error: raise ValidationError(str(error))
        materials.add(r.material_id);ids.append({'revision':r.pk})
    result['items']=ids
    if strict and (not result['cover'] or not previews or not items): raise ValidationError('发布需要封面、至少一张展示图及一张贴纸')
    return result


def admin_library_json(lib, user):
    from .sync_protocol import sync_summary
    content = lib.current.content if lib.current_id else {}
    draft = getattr(lib, 'draft', None)
    cover = lib._list_cover if hasattr(lib, '_list_cover') else ResourceBlob.objects.filter(pk=content.get('cover')).first()
    total = lib.total_members if hasattr(lib, 'total_members') else (lib.current.items.count() if lib.current_id else 0)
    effective = lib.effective_members if hasattr(lib, 'effective_members') else (lib.current.items.filter(material__active=True).count() if lib.current_id else 0)
    template_enabled = not lib.template_id or (lib.template.active and lib.template.series.active)
    available = bool(lib.current_id and lib.active and template_enabled)
    reason = ('尚未发布' if not lib.current_id else '素材包已下架' if not lib.active else
              '关联模板或系列已停用' if not template_enabled else '待完善封面与展示信息' if not content else '')
    return dict(
        id=str(lib.pk), title=content.get('title',lib.title), type=lib.library_type,
        production_sync=sync_summary(lib) if user.has_perm('material_library.sync_materiallibrary') else None,
        template_id=str(lib.template_id) if lib.template_id else None,
        origin_type='template' if lib.template_id else 'independent',
        version=lib.current.number if lib.current_id else 0, count=effective,
        active=lib.active, state_revision=lib.state_revision, featured=lib.featured,
        sort_order=lib.sort_order, new_until=lib.new_until,
        availability='published' if available else 'unavailable',
        cover=blob_json(cover) if cover else None,
        publication_state='draft' if not lib.current_id else ('published' if lib.active else 'withdrawn'),
        has_draft_changes=bool(draft and (not lib.current_id or draft.content != content)),
        gallery_visible=available and bool(content), display_reason=reason,
        template_title=lib.template.title if lib.template_id else None,
        total_count=total,
        uploads_enabled=upload_status()[0],upload_unavailable_reason=upload_status()[1],
        updated_at=draft.updated_at if draft else (lib.current.created_at if lib.current_id else None),
        updated_by=draft.actor.get_username() if draft and draft.actor else None,
    )


def prepare_library_page(rows, user):
    """Aggregate only the selected page, without grouping wide related JSON rows."""
    versions = [row.current_id for row in rows if row.current_id]
    counts = {row['version_id']: row for row in LibraryItem.objects.filter(
        version_id__in=versions).order_by().values('version_id').annotate(
            total=Count('id'), effective=Count('id', filter=Q(material__active=True)))}
    covers = ResourceBlob.objects.in_bulk({row.current.content.get('cover') for row in rows
                                         if row.current_id and row.current.content.get('cover')})
    tasks = {}
    if user.has_perm('material_library.sync_materiallibrary'):
        latest = MaterialSyncTask.objects.filter(side='source', library_uuid=OuterRef('library_uuid')).order_by('-created_at', '-id')
        tasks = {task.library_uuid: task for task in MaterialSyncTask.objects.filter(
            side='source', library_uuid__in=[row.pk for row in rows],
            pk=Subquery(latest.values('pk')[:1])).defer('snapshot')}
    for row in rows:
        count = counts.get(row.current_id, {})
        row.total_members = count.get('total', 0)
        row.effective_members = count.get('effective', 0)
        row._list_cover = covers.get(row.current.content.get('cover')) if row.current_id else None
        row._list_sync_task = tasks.get(row.pk)


def admin_page(request, rows, serialize, prepare=None):
    # Opt-in pagination preserves existing administrative integrations.
    if request.query_params.get('paged') != '1':
        selected = list(rows[:500])
        if prepare: prepare(selected)
        return Response([serialize(row) for row in selected])
    page = serializers.IntegerField(min_value=1).run_validation(request.query_params.get('page', 1))
    size = serializers.IntegerField(min_value=1, max_value=100).run_validation(request.query_params.get('page_size', 20))
    pager = Paginator(rows, size)
    current = pager.get_page(page)
    selected = list(current.object_list)
    if prepare: prepare(selected)
    return Response(dict(items=[serialize(row) for row in selected], total=pager.count,
                         page=current.number, page_size=size))


class Options(Admin):
    def get(self, request):
        user = request.user
        legacy = user.is_superuser or user.has_perm('diary_presets.change_template')
        return Response(dict(user_id=user.pk, uploads_enabled=upload_status()[0],upload_unavailable_reason=upload_status()[1],
            can_edit=legacy or user.has_perm('material_library.change_materiallibrary'),
            can_publish=legacy or user.has_perm('material_library.publish_materiallibrary'),
            can_takedown=legacy or user.has_perm('material_library.takedown_materiallibrary')))


class Templates(Admin):
    def get(self, request):
        from diary_presets.models import Template
        qs = Template.objects.filter(audience='public').select_related('current','series')
        if q := request.query_params.get('q'): qs = qs.filter(title__icontains=q)
        typ = request.query_params.get('type', 'sticker')
        if typ not in ('sticker', 'background'): raise ValidationError('无效类型')
        qs = qs.exclude(material_libraries__library_type=typ).order_by('title','id')
        return admin_page(request, qs, lambda t: dict(id=str(t.pk), title=t.title,
            series=t.series.title, version=t.current.number if t.current_id else 0, active=t.active))


class Libraries(Admin):
    def get(self,request):
        qs=public_libraries().select_related('template__series','current','draft__actor').order_by('sort_order','id')
        if q:=request.query_params.get('q'): qs=qs.filter(title__icontains=q)
        if t:=request.query_params.get('type'):
            if t not in ('sticker','background'): raise ValidationError('无效类型')
            qs=qs.filter(library_type=t)
        origin=request.query_params.get('origin')
        if origin and origin not in ('independent','template'): raise ValidationError('无效来源')
        if origin: qs=qs.filter(template__isnull=origin=='independent')
        state=request.query_params.get('state')
        if state and state not in ('draft','published','withdrawn'): raise ValidationError('无效状态')
        if state=='draft': qs=qs.filter(current__isnull=True)
        elif state=='published': qs=qs.filter(current__isnull=False,active=True)
        elif state=='withdrawn': qs=qs.filter(current__isnull=False,active=False)
        return admin_page(request,qs,lambda l:admin_library_json(l,request.user),
                          prepare=lambda rows:prepare_library_page(rows,request.user))
    @transaction.atomic
    def post(self,request):
        title=clean_text(request.data.get('title'),60,True)
        typ=request.data.get('type','sticker')
        if typ not in ('sticker','background'): raise ValidationError('无效类型')
        template=None
        if request.data.get('template_id'):
            from diary_presets.models import Template
            template=get_object_or_404(Template,pk=serializers.UUIDField().run_validation(request.data['template_id']),audience='public')
            if MaterialLibrary.objects.filter(template=template,library_type=typ).exists(): raise Conflict('模板已有关联主库')
        lib=MaterialLibrary.objects.create(title=title,library_type=typ,template=template)
        LibraryDraft.objects.create(library=lib,content=draft_content(lib),actor=request.user)
        audit(request,lib,'create',{})
        return Response(admin_library_json(lib,request.user),status=201)


class Draft(Admin):
    def get(self,request,pk):
        lib=get_object_or_404(public_libraries(),pk=pk)
        d,_=LibraryDraft.objects.get_or_create(library=lib,defaults={'content':draft_content(lib),'base_version':lib.current.number if lib.current_id else 0})
        rows=MaterialRevision.objects.filter(pk__in=[i['revision'] for i in d.content.get('items',[])]).select_related('resource','thumbnail','material')
        previews={b.pk:blob_json(b) for b in ResourceBlob.objects.filter(pk__in=[d.content.get('cover')]+d.content.get('previews',[]))}
        latest = {}
        for row in MaterialRevision.objects.filter(material_id__in=[r.material_id for r in rows], material__active=True).select_related('resource','thumbnail','material').order_by('-pk'):
            latest.setdefault(str(row.material_id), item_json(type('Item',(),{'revision':row})(),request.user))
        bindings = list(TemplateLibraryBinding.objects.filter(library_version__library=lib).values('preset_version__number','library_version__number'))
        return Response(dict(latest_items=list(latest.values()),bindings=bindings,uploads_enabled=upload_status()[0],upload_unavailable_reason=upload_status()[1],content=d.content,revision=d.revision,base_version=d.base_version,items=[item_json(type('Item',(),{'revision':r})(),request.user) for r in rows],images=previews))
    @transaction.atomic
    def patch(self,request,pk):
        lib=get_object_or_404(public_libraries().select_for_update(),pk=pk)
        d=get_object_or_404(LibraryDraft,library=lib)
        if request.data.get('expected_draft_revision')!=d.revision: raise Conflict()
        d.content=clean_content(request.data.get('content'),lib);d.revision+=1;d.actor=request.user;d.save()
        for title in d.content.get('tags',[]): MaterialTag.objects.get_or_create(title=title)
        audit(request,lib,'draft',{'revision':d.revision})
        return Response(dict(revision=d.revision,base_version=d.base_version))


class Validate(Admin):
    def post(self,request,pk):
        d=get_object_or_404(LibraryDraft,library_id=pk)
        if request.data.get('expected_draft_revision')!=d.revision: raise Conflict()
        clean_content(d.content,d.library,True)
        return Response(dict(errors=[],warnings=[],count=len(d.content['items']),
            previous_count=d.library.current.items.count() if d.library.current_id else 0,
            next_version=d.base_version+1, active=d.library.active,
            template_title=d.library.template.title if d.library.template_id else None))


class Publish(Admin):
    @transaction.atomic
    def post(self,request,pk):
        lib=get_object_or_404(public_libraries().select_for_update(),pk=pk)
        key=clean_text(request.data.get('idempotency_key'),100,True)
        digest=hashlib.sha256(json.dumps(request.data,sort_keys=True).encode()).hexdigest()
        job=MaterialPublishJob.objects.filter(library=lib,key=key).first()
        if job:
            if job.digest!=digest: raise Conflict('幂等键已用于另一请求')
            return Response({'version':job.version.number})
        d=get_object_or_404(LibraryDraft,library=lib)
        actual=lib.current.number if lib.current_id else 0
        if request.data.get('expected_version')!=actual or request.data.get('expected_draft_revision')!=d.revision: raise Conflict()
        content=clean_content(d.content,lib,True)
        if lib.template_id and not lib.template.current_id: raise ValidationError('请先发布模板')
        v=LibraryVersion.objects.create(library=lib,number=actual+1,preset_version=lib.template.current if lib.template_id else None,content=content)
        rows={r.pk:r for r in MaterialRevision.objects.filter(pk__in=[i['revision'] for i in content['items']])}
        LibraryItem.objects.bulk_create([LibraryItem(version=v,revision=rows[i['revision']],material_id=rows[i['revision']].material_id,position=n) for n,i in enumerate(content['items'])])
        if lib.template_id:
            TemplateLibraryBinding.objects.get_or_create(preset_version=lib.template.current,library_type=lib.library_type,defaults={'library_version':v})
        lib.current=v;lib.title=content['title'];lib.state_revision+=1
        if lib.first_published_at is None: lib.first_published_at=timezone.now()
        lib.save()
        d.base_version=v.number;d.revision+=1;d.save()
        MaterialPublishJob.objects.create(library=lib,key=key,digest=digest,version=v)
        audit(request,lib,'publish',{'version':v.number,'key':key})
        return Response({'version':v.number})


class Availability(Admin):
    @transaction.atomic
    def post(self,request,pk):
        lib=get_object_or_404(public_libraries().select_for_update(),pk=pk)
        if request.data.get('expected_state_revision')!=lib.state_revision: raise Conflict()
        active=request.data.get('active')
        if not isinstance(active,bool): raise ValidationError('active 必须为布尔值')
        lib.active=active;lib.state_revision+=1;lib.save(update_fields=['active','state_revision'])
        audit(request,lib,'availability',{'active':active})
        return Response({'state_revision':lib.state_revision})


class Placement(Admin):
    @transaction.atomic
    def patch(self,request,pk):
        lib=get_object_or_404(public_libraries().select_for_update(),pk=pk)
        if request.data.get('expected_state_revision')!=lib.state_revision: raise Conflict()
        if 'featured' in request.data: lib.featured=serializers.BooleanField().run_validation(request.data['featured'])
        if 'sort_order' in request.data: lib.sort_order=serializers.IntegerField().run_validation(request.data['sort_order'])
        if 'new_until' in request.data: lib.new_until=serializers.DateTimeField(allow_null=True).run_validation(request.data['new_until'])
        lib.state_revision+=1;lib.save();audit(request,lib,'placement',dict(request.data))
        return Response({'state_revision':lib.state_revision})


class Versions(Admin):
    def get(self,request,pk):
        lib=get_object_or_404(public_libraries(),pk=pk)
        return Response([{'version':v.number,'created_at':v.created_at,'content':v.content} for v in lib.versions.order_by('-number')])


class Restore(Admin):
    @transaction.atomic
    def post(self,request,pk):
        lib=get_object_or_404(public_libraries().select_for_update(),pk=pk)
        d=get_object_or_404(LibraryDraft,library=lib)
        if request.data.get('expected_draft_revision')!=d.revision: raise Conflict()
        v=get_object_or_404(lib.versions,number=serializers.IntegerField(min_value=1).run_validation(request.data.get('version')))
        d.content=dict(v.content) if v.content else dict(draft_content(lib),items=[{'revision':r} for r in v.items.values_list('revision_id',flat=True)])
        d.revision+=1;d.save();audit(request,lib,'restore-draft',{'version':v.number})
        return Response({'revision':d.revision})


class Materials(Admin):
    def get(self,request):
        latest=Material.objects.annotate(latest=Max('revisions__pk')).values('latest')
        qs=MaterialRevision.objects.filter(pk__in=latest).select_related('resource','thumbnail','material').order_by('-pk')
        if q:=request.query_params.get('q'): qs=qs.filter(name__icontains=q)
        if t:=request.query_params.get('type'): qs=qs.filter(material__material_type=t)
        if active:=request.query_params.get('active'):
            if active not in ('0','1'): raise ValidationError('无效素材状态')
            qs=qs.filter(material__active=active=='1')
        def serialize(r):
            data=item_json(type('Item',(),{'revision':r})(),request.user)
            data['active']=r.material.active
            return data
        return admin_page(request,qs,serialize)
    @transaction.atomic
    def post(self,request):
        upload=get_object_or_404(MaterialUpload,pk=serializers.UUIDField().run_validation(request.data.get('upload_id')),state='verified')
        if upload.purpose not in ('sticker','background'): raise ValidationError('该文件不是单张素材')
        m,_=Material.objects.get_or_create(source_identity='upload:'+str(upload.pk),defaults={'material_type':upload.purpose})
        r=revision(m,dict(name=clean_text(request.data.get('name',upload.name),60,True),kind=request.data.get('kind','illustration'),subcategory=request.data.get('subcategory','object'),keywords=request.data.get('keywords',[]),aliases=request.data.get('aliases',[]),resource_id=upload.resource_id,thumbnail_id=upload.thumbnail_id,sources=[]))
        return Response(item_json(type('Item',(),{'revision':r})(),request.user),status=201)


class MaterialUsage(Admin):
    def get(self, request, pk):
        material=get_object_or_404(Material, pk=pk)
        rows=LibraryItem.objects.filter(material=material).filter(
            Q(version_id=F('version__library__current_id')) | Q(version__template_bindings__isnull=False)
        ).select_related('version__library__template').distinct().order_by('version__library__title','-version__number')
        result=[]
        for row in rows:
            lib=row.version.library
            result.append(dict(library_id=str(lib.pk),title=lib.title,version=row.version.number,
                revision=row.revision_id,current=lib.current_id==row.version_id,active=lib.active,
                template=lib.template.title if lib.template_id else None,
                template_versions=list(row.version.template_bindings.values_list('preset_version__number',flat=True))))
        return Response(dict(material_id=str(material.pk),items=result,
            note='列出当前发布包及固定模板引用；历史作品持有自己的资源，草稿需在发布前重新校验。'))


class Revisions(Admin):
    @transaction.atomic
    def post(self,request,pk):
        m=get_object_or_404(Material.objects.select_for_update(),pk=pk)
        r=get_object_or_404(m.revisions,pk=serializers.IntegerField(min_value=1).run_validation(request.data.get('revision')))
        latest=m.revisions.order_by('-pk').first()
        if latest and latest.pk != r.pk:raise Conflict('素材已有新版本，请刷新后修改')
        data={k:getattr(r,k) for k in ('name','kind','subcategory','keywords','aliases','resource_id','thumbnail_id','sources')}
        for k in ('name','kind','subcategory','keywords','aliases'):
            if k in request.data:data[k]=request.data[k]
        if request.data.get('upload_id'):
            u=get_object_or_404(MaterialUpload,pk=serializers.UUIDField().run_validation(request.data['upload_id']),state='verified',purpose=m.material_type)
            data.update(resource_id=u.resource_id,thumbnail_id=u.thumbnail_id)
        data['name']=clean_text(data['name'],60,True)
        for key in ('keywords','aliases'):
            values=data[key]
            if not isinstance(values,list) or len(values)>20 or any(not isinstance(v,str) or len(v)>30 for v in values):raise ValidationError('关键词和别名各最多 20 项，每项 30 字')
        new=revision(m,data)
        audit(request,None,'material-revision',{'material':str(m.pk),'revision':new.pk})
        return Response(item_json(type('Item',(),{'revision':new})(),request.user))


class MaterialAvailability(Admin):
    @transaction.atomic
    def post(self,request,pk):
        m=get_object_or_404(Material.objects.select_for_update(),pk=pk)
        active=request.data.get('active')
        if not isinstance(active,bool):raise ValidationError('active 必须为布尔值')
        if request.data.get('expected_active') is not None and request.data['expected_active'] != m.active: raise Conflict()
        m.active=active;m.save()
        audit(request,None,'material-availability',{'material':str(m.pk),'active':active})
        return Response({'active':active,'libraries':list(MaterialLibrary.objects.filter(versions__items__material=m).values_list('id',flat=True).distinct())})


class UploadThrottle(UserRateThrottle):
    scope='material_upload'
    rate='120/hour'


def upload_json(upload):
    return dict(id=str(upload.pk),state=upload.state,error=upload.error,
        confirmation='oss-metadata',resource=blob_json(upload.resource) if upload.resource_id else None,
        thumbnail=blob_json(upload.thumbnail) if upload.thumbnail_id else None)


class Uploads(Admin):
    throttle_classes=[UploadThrottle]
    def post(self,request):
        enabled,reason=upload_status()
        if not enabled: raise ValidationError(reason)
        if MaterialUpload.objects.filter(actor=request.user,state__in=['created','queued','validating'],expires_at__gt=timezone.now()).count()>=100:
            raise ValidationError('待处理文件超过 100 个，请完成已有文件后重试')
        purpose=request.data.get('purpose')
        if purpose not in ('sticker','background','cover','preview'):raise ValidationError('无效文件用途')
        original=metadata(request.data.get('original'),purpose)
        thumb=metadata(request.data.get('thumbnail'),purpose,thumbnail=True)
        ratio=min(1,256/max(original['width'],original['height']))
        if (thumb['width'],thumb['height'])!=(max(1,int(original['width']*ratio+0.5)),max(1,int(original['height']*ratio+0.5))):
            raise ValidationError('缩略图尺寸或比例不符合原图')
        upload=MaterialUpload(id=uuid.uuid4(),actor=request.user,purpose=purpose,
            name=clean_text(request.data.get('name'),120,True),byte_size=original['byte_size'],sha256=original['sha256'],
            upload_metadata={'protocol':2,'original':original,'thumbnail':thumb},expires_at=timezone.now()+timedelta(hours=1))
        upload.object_key=prefix()+'material-uploads/'+str(upload.pk)+'/original'
        plan=upload_plan(upload);upload.save()
        return Response(dict(id=str(upload.pk),uploads=plan,expires_at=upload.expires_at),status=201)


class UploadDetail(Admin):
    def get(self,request,pk):
        upload=get_object_or_404(MaterialUpload,pk=pk,actor=request.user)
        return Response(upload_json(upload))


class UploadComplete(Admin):
    def post(self,request,pk):
        return Response(upload_json(confirm_upload(pk,request.user)))


class Audit(Admin):
    def get(self,request):
        qs=MaterialAudit.objects.order_by('-id')
        if lib:=request.query_params.get('library'):qs=qs.filter(library_id=lib)
        return Response(list(qs.values('id','actor_id','library_id','action','detail','created_at')[:200]))


class Dictionary(Admin):
    def get(self,request,target):
        if target=='tags':return Response(list(MaterialTag.objects.order_by('title').values('id','title','active')))
        from .catalog import CATEGORIES
        rows={(kind,sub):dict(id=None,kind=kind,subcategory=sub,title=title,active=True,position=index) for kind,(_,subs) in CATEGORIES.items() for index,(sub,title) in enumerate(subs.items())}
        for r in MaterialCategory.objects.order_by('kind','position','subcategory'):
            rows[(r.kind,r.subcategory)]=dict(id=r.pk,kind=r.kind,subcategory=r.subcategory,title=r.title,active=r.active,position=r.position)
        return Response(list(rows.values()))
    def post(self,request,target):return self.save(request,target)
    def patch(self,request,target):return self.save(request,target)
    @transaction.atomic
    def save(self,request,target):
        title=clean_text(request.data.get('title'),30 if target=='tags' else 60,True)
        active=serializers.BooleanField().run_validation(request.data.get('active',True))
        if target=='tags':
            if request.data.get('id'):
                obj=get_object_or_404(MaterialTag,pk=request.data['id']);obj.title=title;obj.active=active;obj.save()
            else:obj,_=MaterialTag.objects.get_or_create(title=title,defaults={'active':active})
        else:
            from .catalog import CATEGORIES
            kind=request.data.get('kind');sub=request.data.get('subcategory')
            import re
            if kind not in CATEGORIES or not isinstance(sub,str) or not re.fullmatch('[a-z][a-z0-9_]{0,31}',sub):raise ValidationError('无效分类标识')
            obj,_=MaterialCategory.objects.update_or_create(kind=kind,subcategory=sub,defaults={'title':title,'active':active,'position':serializers.IntegerField().run_validation(request.data.get('position',0))})
        audit(request,None,'dictionary',{'target':target,'id':obj.pk,'active':active})
        return Response({'id':obj.pk})
