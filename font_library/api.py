import uuid
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework import serializers
from common.permissions import AdminCodePermission
from .models import *
from . import services, storage
from .schemas import UploadInput

class Base(APIView):
    permission_classes=[IsAuthenticated]

class Admin(Base):
    permission_classes=[AdminCodePermission]
    @property
    def required_permission_code(self):
        action=self.kwargs.get('action','')
        if action in ('publish','validate'): return 'font_library.publish_fontfamily'
        if action=='availability': return 'font_library.takedown_fontfamily'
        return 'font_library.view_fontfamily' if self.request.method=='GET' else 'font_library.change_fontfamily'

def asset_json(asset):
    return dict(id=str(asset.pk),kind=asset.kind,sha256=asset.sha256,byte_size=asset.byte_size,mime=asset.mime,metadata=asset.metadata,
                url=storage.sign(asset.object_key) if asset.kind in ('cover','preview') else None)

def family_json(f, request, admin=False):
    content=f.current.content if f.current_id else {'title':f.title}
    images={str(a.pk):storage.sign(a.object_key) for a in f.current.assets.filter(kind__in=['cover','preview'])} if f.current_id else {}
    row=dict(id=str(f.pk),title=content['title'],version=f.current.number if f.current_id else 0,active=f.active,featured=f.featured,sort_order=f.sort_order,
             content=content,images=images,updated_at=f.updated_at)
    if admin:
        from .sync_protocol import sync_summary
        row.update(state_revision=f.state_revision,production_sync=sync_summary(f),has_draft_changes=hasattr(f,'fontdraft') and (not f.current_id or f.fontdraft.content!=f.current.content))
    if not admin: row.update(services.access(request,f))
    return row

class Options(Admin):
    def get(self,request):
        from backoffice.rbac import has_permission_code
        def allowed(code): return request.user.is_superuser or has_permission_code(request.user.pk,code)
        return Response(dict(max_file_size=100*1024*1024,formats=['ttf','otf'],processor_configured=bool(settings.FONT_PROCESSOR_TOKEN),
          permissions={key:allowed('font_library.'+code+'_fontfamily') for key,code in [('edit','change'),('publish','publish'),('takedown','takedown'),('upload','upload')]}))

class Families(Admin):
    def get(self,request):
        qs=FontFamily.objects.select_related('current').order_by('sort_order','id')
        if request.query_params.get('q'): qs=qs.filter(title__icontains=request.query_params['q'])
        state=request.query_params.get('state')
        if state=='draft':qs=qs.filter(current=None)
        elif state=='published':qs=qs.filter(active=True,current__isnull=False)
        elif state=='withdrawn':qs=qs.filter(active=False,current__isnull=False)
        page=serializers.IntegerField(min_value=1).run_validation(request.query_params.get('page',1))
        return Response(dict(count=qs.count(),items=[family_json(f,request,True) for f in qs[(page-1)*20:page*20]]))
    @transaction.atomic
    def post(self,request):
        title=serializers.CharField(max_length=120).run_validation(request.data.get('title'))
        f=FontFamily.objects.create(title=title)
        FontDraft.objects.create(family=f,content=services.normalize({'title':title}),actor=request.user)
        FontAudit.objects.create(family=f,actor=request.user,action='create')
        return Response({'id':str(f.pk)},status=201)

class FamilyAdmin(Admin):
    def get(self,request,pk,action):
        f=get_object_or_404(FontFamily,pk=pk)
        if action=='draft':
            d=f.fontdraft
            return Response(dict(family=family_json(f,request,True),revision=d.revision,base_version=d.base_version,content=d.content,
                assets=[asset_json(a) for a in FontAsset.objects.filter(family=f)],uploads=[upload_json(u) for u in FontUpload.objects.filter(family=f).order_by('-updated_at')[:100]]))
        if action=='versions': return Response({'items':list(f.releases.order_by('-number').values('number','created_at','content'))})
        if action=='audit': return Response({'items':list(FontAudit.objects.filter(family=f).order_by('-created_at').values('action','detail','created_at')[:100])})
        raise ValidationError('未知操作')
    @transaction.atomic
    def patch(self,request,pk,action):
        f=get_object_or_404(FontFamily.objects.select_for_update(),pk=pk)
        if action=='draft':
            d=FontDraft.objects.select_for_update().get(family=f)
            if request.data.get('expected_revision')!=d.revision: return Response({'detail':'草稿已变化，请重新加载'},status=409)
            d.content=services.normalize(request.data.get('content'));d.revision+=1;d.actor=request.user;d.save()
            FontAudit.objects.create(family=f,actor=request.user,action='save_draft',detail={'revision':d.revision})
            return Response({'revision':d.revision})
        if action=='availability':
            active=serializers.BooleanField().run_validation(request.data.get('active'))
            if active:
                if not f.current_id: raise ValidationError('请先发布字体')
                errors,_=services.issues(f,f.current.content)
                if errors:raise ValidationError(errors)
            f.active=active;f.state_revision+=1;f.save()
        elif action=='placement':
            f.featured=serializers.BooleanField().run_validation(request.data.get('featured',f.featured))
            f.sort_order=serializers.IntegerField().run_validation(request.data.get('sort_order',f.sort_order));f.save()
        else:raise ValidationError('未知操作')
        FontAudit.objects.create(family=f,actor=request.user,action=action,detail=dict(request.data))
        return Response({'ok':True})
    def post(self,request,pk,action):
        f=get_object_or_404(FontFamily,pk=pk)
        if action=='validate':return Response({'issues':services.issues(f,f.fontdraft.content)[0]})
        if action=='publish':
            key=serializers.CharField(max_length=100).run_validation(request.data.get('key'))
            release=services.publish(pk,request.data.get('expected_revision'),request.data.get('base_version'),key,request.user)
            return Response({'version':release.number})
        if action=='restore':
            with transaction.atomic():
                FontFamily.objects.select_for_update().get(pk=pk)
                d=FontDraft.objects.select_for_update().get(family=f)
                if d.revision!=request.data.get('expected_revision'):return Response({'detail':'草稿已变化'},status=409)
                old=get_object_or_404(FontRelease,family=f,number=request.data.get('version'))
                d.content=old.content;d.revision+=1;d.actor=request.user;d.save()
                FontAudit.objects.create(family=f,actor=request.user,action='restore_draft',detail={'version':old.number})
            return Response({'revision':d.revision})
        raise ValidationError('未知操作')

def upload_json(u):
    return dict(id=str(u.pk),name=u.name,kind=u.kind,state=u.state,error=u.error,asset_id=str(u.asset_id) if u.asset_id else None)

class Uploads(Admin):
    required_permission_code='font_library.upload_fontfamily'
    def post(self,request):
        form=UploadInput(data=request.data);form.is_valid(raise_exception=True);v=form.validated_data
        f=get_object_or_404(FontFamily,pk=v.pop('family'));identifier=uuid.uuid4()
        u=FontUpload.objects.create(id=identifier,family=f,actor=request.user,declared_sha256=v.pop('sha256'),object_key=storage.prefix()+f'uploads/{identifier}/source',expires_at=timezone.now()+timedelta(hours=1),**v)
        headers={'Content-Type':u.mime,'Content-MD5':u.md5}
        return Response(dict(upload=upload_json(u),url=storage.sign(u.object_key,'PUT',headers),headers=headers),status=201)

class UploadComplete(Uploads):
    @transaction.atomic
    def post(self,request,pk):
        u=get_object_or_404(FontUpload.objects.select_for_update(),pk=pk,actor=request.user)
        if u.state in ('queued','processing','ready'):return Response(upload_json(u))
        if u.state=='failed' and u.candidate_key:
            u.state='queued';u.error='';u.save();return Response(upload_json(u))
        if u.expires_at<=timezone.now():raise ValidationError('上传会话已过期，请重新上传')
        u.candidate_key,u.etag=storage.freeze(u);u.state='queued';u.save()
        return Response(upload_json(u))

class Catalog(Base):
    def get(self,request,pk=None):
        if pk:
            f=get_object_or_404(FontFamily.objects.select_related('current'),pk=pk,current__isnull=False)
            if not f.active and not services.access(request,f)['access']['permanently_owned']:raise PermissionDenied('字体已下架')
            return Response(family_json(f,request))
        qs=FontFamily.objects.filter(active=True,current__isnull=False).select_related('current')
        if request.query_params.get('q'):qs=qs.filter(title__icontains=request.query_params['q'])
        qs=qs.order_by('-first_published_at','id') if request.query_params.get('sort')=='latest' else qs.order_by('-featured','sort_order','id')
        page=serializers.IntegerField(min_value=1).run_validation(request.query_params.get('page',1))
        return Response({'count':qs.count(),'items':[family_json(f,request) for f in qs[(page-1)*30:page*30]]})

class Personal(Base):
    def get(self,request):
        ids=set(FontPersonalEntry.objects.filter(user=request.user).filter(Q(acquired=True)|Q(favorite=True)).values_list('family_id',flat=True))
        if request.headers.get('X-Billing-Session'):
            from billing.identity import identity_for
            from billing.models import ContentOwnership
            owned=ContentOwnership.objects.filter(identity=identity_for(request),target_kind='font',state='active').values_list('target_id',flat=True)
            ids.update(owned)
            for fid in owned:
                if FontFamily.objects.filter(pk=fid).exists():
                    FontPersonalEntry.objects.update_or_create(user=request.user,family_id=fid,defaults={'acquired':True})
        rows=[]
        for f in FontFamily.objects.filter(pk__in=ids,current__isnull=False).select_related('current'):
            row=family_json(f,request);p=FontPersonalEntry.objects.get(user=request.user,family=f)
            row.update(favorite=p.favorite,acquired=p.acquired);rows.append(row)
        return Response({'items':rows})
    @transaction.atomic
    def post(self,request,pk,action):
        f=get_object_or_404(FontFamily.objects.select_for_update(),pk=pk,current__isnull=False)
        a=services.access(request,f)
        p,_=FontPersonalEntry.objects.get_or_create(user=request.user,family=f)
        if action=='favorite':p.favorite=serializers.BooleanField().run_validation(request.data.get('favorite',True))
        elif action=='claim':
            if not f.active or not a['access']['can_use']:raise PermissionDenied('当前不能获取字体')
            p.acquired=True
            if a['access']['reason']=='free':
                p.free_claimed=True;p.claim_policy_revision=a['commerce']['policy_revision']
        else:raise ValidationError('未知操作')
        p.save();return Response({'ok':True})

class Download(Base):
    @transaction.atomic
    def post(self,request):
        f=get_object_or_404(FontFamily,pk=serializers.UUIDField().run_validation(request.data.get('font_id')))
        version=serializers.IntegerField(min_value=1).run_validation(request.data.get('version'))
        release=get_object_or_404(FontRelease,family=f,number=version)
        face=next((x for x in release.content['faces'] if x['id']==request.data.get('face_id')),None)
        if not face:raise ValidationError('字面不存在')
        a=services.access(request,f);purpose=request.data.get('purpose','use')
        doc=serializers.UUIDField().run_validation(request.data.get('document_id')) if request.data.get('document_id') else None
        if purpose=='restore':
            if not doc or not FontUsageGrant.objects.filter(user=request.user,document_id=doc,release=release,face_id=face['id']).exists():raise PermissionDenied('缺少历史作品授权依据')
        elif purpose=='use':
            if not a['access']['can_use']:raise PermissionDenied('请先获取或解锁字体')
        else:raise ValidationError('无效使用目的')
        asset=get_object_or_404(release.assets,pk=face['asset_id'],kind='font')
        grant=None
        if doc:
            grant,_=FontUsageGrant.objects.get_or_create(user=request.user,document_id=doc,release=release,face_id=face['id'],defaults={'source':a['access']['reason']})
        defaults={'acquired':True}
        if purpose=='use' and a['access']['reason']=='free':
            defaults.update(free_claimed=True,claim_policy_revision=a['commerce']['policy_revision'])
        FontPersonalEntry.objects.update_or_create(user=request.user,family=f,defaults=defaults)
        return Response(dict(font_id=str(f.pk),version=str(version),face_id=face['id'],postscript_name=face['postscript_name'],display_name=release.content['title'],
            url=storage.sign(asset.object_key),sha256=asset.sha256,byte_size=asset.byte_size,mime=asset.mime,expires_in=900,usage_grant=str(grant.pk) if grant else None))
