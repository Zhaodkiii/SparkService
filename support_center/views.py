import uuid
import re
from datetime import timedelta
from django.db import transaction
from django.db.models import Q,F
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny,IsAuthenticated
from rest_framework.exceptions import ValidationError,PermissionDenied,NotFound,APIException,MethodNotAllowed
from rest_framework.response import Response
from rest_framework import serializers
from .models import Config,Category,Article,ArticleVersion,Ticket,Message,Attachment,Operation,Audit
from .services import *
from .constraints import SUBMISSION_LIMITS
from .throttles import HelpReadThrottle,SupportRequestThrottle

class Public(APIView):
    permission_classes=[AllowAny]
    throttle_classes=[HelpReadThrottle]
class Private(APIView):
    permission_classes=[IsAuthenticated]
    throttle_classes=[SupportRequestThrottle]
    def check_permissions(self,request):
        super().check_permissions(request)
        from django.conf import settings
        if request.auth is not None and not (request.user.is_staff or request.user.is_superuser):
            bundle=str(request.auth.get('bundle_id',''))
            if bundle not in getattr(settings,'SUPPORT_ALLOWED_BUNDLE_IDS',['cn.zhaodk.TravelDiary']):
                raise PermissionDenied('当前应用不可访问此服务')


def configuration(): return Config.objects.get_or_create(key='traveldiary')[0]
def page(request,qs,encode):
    offset=integer(request.query_params.get('cursor'));limit=max(1,integer(request.query_params.get('limit'),20,50))
    rows=list(qs[offset:offset+limit+1])
    return dict(results=[encode(x) for x in rows[:limit]],next_cursor=str(offset+limit) if len(rows)>limit else None)
def article_data(a,admin=False):
    result=dict(id=str(a.pk),category=a.category.code,**(a.draft if admin else a.published),updated_at=a.published_at)
    if admin: result.update(revision=a.revision,live=a.live,draft=a.draft,published=a.published)
    return result

def version_tuple(s):
    return tuple(integer(x,maximum=999999) for x in str(s).split('.')[:4])+(0,)*(4-len(str(s).split('.')[:4]))
def applicable(a,request):
    v=version_tuple(request.query_params.get('version','0'));d=a.published
    return (not d.get('min_version') or v>=version_tuple(d['min_version'])) and (not d.get('max_version') or v<=version_tuple(d['max_version'])) and d.get('language','zh-Hans')==request.query_params.get('language','zh-Hans')

class Paused(APIException):
    status_code=503

class Configuration(Public):
    admin=False
    def get(self,request):
        c=configuration()
        if self.admin: demand(request.user,'manage_config')
        d=dict(accepting=c.accepting,pause_message=c.pause_message,service_hours=c.service_hours,contact=c.contact,types=c.types,revision=c.revision,submission_limits=SUBMISSION_LIMITS)
        if self.admin:d.update(templates=c.templates,retention_days=c.retention_days)
        return Response(d)
    @transaction.atomic
    def patch(self,request):
        demand(request.user,'manage_config');c=Config.objects.select_for_update().get(pk=configuration().pk);revision(c,request.data)
        class Input(serializers.Serializer):
            accepting=serializers.BooleanField(required=False)
            pause_message=serializers.CharField(max_length=300,allow_blank=True,required=False)
            service_hours=serializers.CharField(max_length=200,allow_blank=True,required=False)
            contact=serializers.CharField(max_length=200,allow_blank=True,required=False)
            retention_days=serializers.IntegerField(min_value=1,max_value=3650,required=False)
            types=serializers.ListField(child=serializers.DictField(),min_length=1,max_length=20,required=False)
            templates=serializers.ListField(child=serializers.CharField(max_length=2000),max_length=30,required=False)
        s=Input(data=request.data);s.is_valid(raise_exception=True);d=s.validated_data
        if 'types' in d:
            codes=set()
            for t in d['types']:
                if not isinstance(t.get('code'),str) or not t['code'].replace('_','').isalnum() or len(t['code'])>60 or t['code'] in codes: raise ValidationError('类型 code 必须唯一且不可为空')
                short_text(t.get('name'),60);codes.add(t['code'])
        for k,v in d.items():setattr(c,k,v)
        if c.accepting and not c.service_hours.strip(): raise ValidationError('开放受理前请填写真实服务时间说明')
        c.revision+=1;c.save();audit(request,'config_updated',revision=c.revision)
        return self.get(request)

class Categories(Public):
    admin=False
    def get(self,request):
        if self.admin:demand(request.user,'edit_help')
        qs=Category.objects.all() if self.admin else Category.objects.filter(active=True)
        return Response([dict(code=c.code,name=c.name,sort=c.sort,active=c.active) for c in qs.order_by('sort','pk')])
    @transaction.atomic
    def post(self,request):
        demand(request.user,'edit_help')
        class Input(serializers.Serializer):
            code=serializers.SlugField(max_length=60)
            name=serializers.CharField(max_length=100)
            sort=serializers.IntegerField(default=0)
            active=serializers.BooleanField(default=True)
        s=Input(data=request.data);s.is_valid(raise_exception=True)
        Category.objects.update_or_create(code=s.validated_data['code'],defaults=s.validated_data);audit(request,'category_updated',code=s.validated_data['code'])
        return self.get(request)

class Articles(Public):
    admin=False
    def get(self,request):
        qs=Article.objects.select_related('category')
        if self.admin:demand(request.user,'edit_help')
        else:qs=qs.filter(live=True,category__active=True)
        if request.query_params.get('category'):qs=qs.filter(category__code=request.query_params['category'])
        q=request.query_params.get('q','')[:200].strip().casefold()
        values=[a for a in qs.order_by('-published_at','id') if (self.admin or applicable(a,request)) and (not q or q in ' '.join(str(x) for x in (a.draft if self.admin else a.published).values()).casefold())]
        values.sort(key=lambda a:(-(a.draft if self.admin else a.published).get('pinned',False), (a.draft if self.admin else a.published).get('sort',0)))
        return Response(page(request,values,lambda a:article_data(a,self.admin)))
    @transaction.atomic
    def post(self,request):
        demand(request.user,'edit_help')
        category=get_object_or_404(Category,code=request.data.get('category'))
        d=validate_article(request.data)
        a=Article.objects.create(category=category,draft=d);audit(request,'article_created',article_id=str(a.pk))
        return Response(article_data(a,True),status=201)

def validate_article(data):
    class Input(serializers.Serializer):
        title=serializers.CharField(max_length=120)
        summary=serializers.CharField(max_length=300,allow_blank=True,default='')
        body=serializers.CharField(max_length=30000)
        keywords=serializers.CharField(max_length=500,allow_blank=True,default='')
        pinned=serializers.BooleanField(default=False)
        sort=serializers.IntegerField(default=0)
        language=serializers.ChoiceField(choices=['zh-Hans','en'],default='zh-Hans')
        min_version=serializers.RegexField(r'^\d+(\.\d+){0,3}$',allow_blank=True,default='')
        max_version=serializers.RegexField(r'^\d+(\.\d+){0,3}$',allow_blank=True,default='')
    s=Input(data=data);s.is_valid(raise_exception=True);d=dict(s.validated_data)
    # Restricted Markdown: images are separately approved help assets; external links are HTTPS only.
    if '<' in d['body'] or 'javascript:' in d['body'].lower():raise ValidationError('帮助正文不支持 HTML 或脚本')
    from urllib.parse import urlparse
    from .models import HelpImage
    for target in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',d['body']):
        if not target.startswith('support-image:'):raise ValidationError('图片须使用帮助图片上传入口')
        try: image_id=uuid.UUID(target.split(':',1)[1])
        except ValueError:raise ValidationError('帮助图片标识无效')
        if not HelpImage.objects.select_for_update().filter(pk=image_id,ready=True).exists():raise ValidationError('帮助图片未准备好')
    no_images=re.sub(r'!\[[^\]]*\]\([^)]+\)','',d['body'])
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',no_images):
        u=urlparse(target)
        if u.scheme!='https' or not u.hostname or u.username:raise ValidationError('帮助链接仅支持 HTTPS')
    if d['min_version'] and d['max_version'] and version_tuple(d['min_version'])>version_tuple(d['max_version']):raise ValidationError('版本范围无效')
    return d

class ArticleDetail(Public):
    admin=False
    def get(self,request,pk):
        a=get_object_or_404(Article.objects.select_related('category'),pk=pk)
        if self.admin:demand(request.user,'edit_help')
        elif not a.live or not a.category.active or not applicable(a,request):return Response({'detail':'文章已下线或不适用于当前版本'},status=410)
        return Response(article_data(a,self.admin))
    @transaction.atomic
    def patch(self,request,pk):
        demand(request.user,'edit_help');a=get_object_or_404(Article.objects.select_for_update(),pk=pk);revision(a,request.data)
        a.category=get_object_or_404(Category,code=request.data.get('category'));a.draft=validate_article(request.data);a.revision+=1;a.save()
        audit(request,'article_edited',article_id=str(pk));return Response(article_data(a,True))
    @transaction.atomic
    def post(self,request,pk,action=None):
        if action is None:raise MethodNotAllowed('POST')
        demand(request.user,'publish_help');a=get_object_or_404(Article.objects.select_for_update(),pk=pk);revision(a,request.data)
        if action=='publish':
            if not a.category.active:raise ValidationError('请先启用分类')
            a.published=validate_article(a.draft);a.live=True;a.ever_published=True;a.published_at=timezone.now()
            ArticleVersion.objects.create(article=a,content=a.published,actor=request.user)
        elif action=='unpublish':a.live=False
        else:raise NotFound()
        a.revision+=1;a.save();audit(request,'article_'+action,article_id=str(pk));return Response(article_data(a,True))

class Versions(Private):
    def get(self,request,pk):
        demand(request.user,'edit_help');a=get_object_or_404(Article,pk=pk)
        return Response(page(request,a.versions.order_by('-pk'),lambda v:dict(id=v.pk,content=v.content,created_at=v.created_at)))

class TicketInput(serializers.Serializer):
    title=serializers.CharField(min_length=1,max_length=SUBMISSION_LIMITS['title_max'])
    description=serializers.CharField(min_length=SUBMISSION_LIMITS['description_min'],max_length=SUBMISSION_LIMITS['description_max'])
    kind=serializers.CharField(max_length=60)
    contact=serializers.CharField(max_length=SUBMISSION_LIMITS['contact_max'],allow_blank=True,default='')
    source=serializers.ChoiceField(choices=['settings','help','order','customization'],default='settings')
    article_id=serializers.UUIDField(required=False,allow_null=True)
    previous_ticket_id=serializers.UUIDField(required=False,allow_null=True)
    related_type=serializers.ChoiceField(choices=['','order','customization'],default='')
    related_id=serializers.UUIDField(required=False,allow_null=True)
    environment=serializers.DictField(child=serializers.CharField(max_length=100),default=dict)
    attachments=serializers.ListField(child=serializers.UUIDField(),max_length=SUBMISSION_LIMITS['attachments_max'],default=list)
    client_request_id=serializers.CharField(max_length=100)

class Tickets(Private):
    admin=False
    def get(self,request):
        qs=tickets(request.user,self.admin)
        state=request.query_params.get('status','')
        if state=='active':qs=qs.exclude(status='closed')
        elif state:qs=qs.filter(status=state)
        if self.admin:
            from django.utils.dateparse import parse_date
            for parameter,field in [('created_from','created_at__date__gte'),('created_to','created_at__date__lte')]:
                if request.query_params.get(parameter):
                    try:date=parse_date(request.query_params[parameter])
                    except (ValueError,TypeError):raise ValidationError('日期格式无效')
                    if not date: raise ValidationError('日期格式无效')
                    qs=qs.filter(**{field:date})
            if request.query_params.get('version'):qs=qs.filter(environment__version=request.query_params['version'])
            for key in ['kind','priority','owner_id','assignee_id']:
                if request.query_params.get(key):
                    value=request.query_params[key]
                    if key.endswith('_id') and not value.isdigit():raise ValidationError('账号标识须为数字')
                    qs=qs.filter(**{key:value})
            if request.query_params.get('unassigned')=='1':qs=qs.filter(assignee__isnull=True)
            if request.query_params.get('user_unread')=='1':qs=qs.filter(last_user_sequence__gt=F('admin_read_sequence'))
            q=request.query_params.get('q','')[:100].strip()
            if q:
                clause=Q(title__icontains=q)
                if q.isdigit():clause|=Q(owner_id=q)
                compact=q.removeprefix('FB').lower()
                if len(compact) in (12,32) and all(c in '0123456789abcdef' for c in compact):
                    ids=[t.pk for t in qs.only('id') if t.id.hex.startswith(compact)];clause|=Q(pk__in=ids)
                qs=qs.filter(clause)
        data=page(request,qs.order_by('-last_public_activity_at','-id'),lambda t:ticket_data(t,request.user,self.admin))
        if not self.admin:data['unread_ticket_count']=summary(request.user)
        return Response(data)
    @transaction.atomic
    def post(self,request):
        if self.admin:raise MethodNotAllowed('POST')
        formal_user(request.user)
        old,op=duplicate(request,'create')
        if old:return Response(ticket_data(get_object_or_404(tickets(request.user),pk=old.result_id)))
        c=configuration()
        if not c.accepting:raise Paused(c.pause_message or '反馈受理暂时关闭，请稍后再试')
        s=TicketInput(data=request.data);s.is_valid(raise_exception=True);d=dict(s.validated_data)
        if d['kind'] not in [v['code'] for v in c.types]:raise ValidationError('请选择有效问题类型')
        now=timezone.now();recent=Ticket.objects.filter(owner=request.user)
        if recent.filter(created_at__gte=now-timedelta(minutes=1)).count()>=3 or recent.filter(created_at__gte=now-timedelta(days=1)).count()>=10:raise Limited()
        rid=d.get('related_id');rt=d.get('related_type')
        if bool(rid)!=bool(rt):raise ValidationError('关联对象不完整')
        if rt:
            if rt=='order':
                from print_orders.models import Order as Related
            else:
                from diary_customizations.models import Request as Related
            get_object_or_404(Related,pk=rid,owner=request.user)
        if d.get('previous_ticket_id'):get_object_or_404(tickets(request.user),pk=d['previous_ticket_id'])
        env=d['environment'];approved={'app','version','build','os','device','language'}
        if set(env)-approved:raise ValidationError('环境信息包含不支持的字段')
        body=d.pop('description');ids=d.pop('attachments');d.pop('client_request_id')
        t=Ticket.objects.create(owner=request.user,**d);add_message(request,t,body,attachments=ids)
        Operation.objects.create(**op,result_id=t.pk);return Response(ticket_data(t),status=201)

class Detail(Private):
    admin=False
    def get(self,request,pk):
        t=get_object_or_404(tickets(request.user,self.admin),pk=pk)
        if self.admin:audit(request,'ticket_viewed',t,contact_visible=permit(request.user,'view_contact'))
        return Response(ticket_data(t,request.user,self.admin))

class Messages(Private):
    admin=False
    def get(self,request,pk):
        t=get_object_or_404(tickets(request.user,self.admin),pk=pk)
        qs=t.messages.prefetch_related('attachments')
        if not self.admin:qs=qs.filter(visibility='public')
        if request.query_params.get('after_sequence'):qs=qs.filter(sequence__gt=integer(request.query_params['after_sequence']))
        return Response(page(request,qs.order_by('created_at','pk'),message_data))
    @transaction.atomic
    def post(self,request,pk):return mutate(request,pk,self.admin,'message')

class Actions(Private):
    admin=False
    @transaction.atomic
    def post(self,request,pk):return mutate(request,pk,self.admin,request.data.get('action',''))

def mutate(request,pk,admin,action):
    old,op=duplicate(request,f'ticket:{pk}')
    t=get_object_or_404(tickets(request.user,admin).select_for_update(),pk=pk)
    if old:return Response(ticket_data(t,request.user,admin))
    revision(t,request.data);before=t.status
    body=request.data.get('body','');ids=request.data.get('attachments',[]);event=''
    if action=='message':
        visibility=request.data.get('visibility','public' if not admin else '')
        if visibility not in ['public','internal'] or (not admin and visibility!='public'):raise ValidationError('请选择公开回复或内部备注')
        capability='note' if visibility=='internal' else 'reply'
        if capability not in allowed(t,request.user,admin):raise PermissionDenied('当前不能回复')
        if body:body=short_text(body)
        elif not ids:raise ValidationError('请填写回复或添加截图')
        if not admin:
            if t.messages.filter(author=request.user,created_at__gte=timezone.now()-timedelta(minutes=1)).count()>=5:raise Limited()
            if t.status!='submitted':t.status='processing'
        elif visibility=='public' and t.status=='submitted':t.status='processing'
    else:
        if action not in allowed(t,request.user,admin):raise PermissionDenied('当前操作不可用')
        visibility='public';event=action
        if action=='accept':t.status='processing';body='工作人员已受理反馈'
        elif action=='request_info':t.status='waiting_user';body=short_text(body)
        elif action=='resolve':t.status='resolved';body=short_text(body)
        elif action=='close':
            t.status='closed';body=short_text(body) if admin else '用户已确认结束反馈'
        elif action=='reopen':t.status='processing';body=short_text(body)
        else:raise ValidationError('未知操作')
    add_message(request,t,body,admin,visibility,event,ids)
    audit(request,'state_transition',t,before=before,after=t.status)
    Operation.objects.create(**op,result_id=t.pk);return Response(ticket_data(t,request.user,admin))

class Read(Private):
    admin=False
    @transaction.atomic
    def post(self,request,pk):
        t=get_object_or_404(tickets(request.user,self.admin).select_for_update(),pk=pk)
        n=integer(request.data.get('through_sequence'));field='admin_read_sequence' if self.admin else 'read_sequence'
        setattr(t,field,max(getattr(t,field),min(n,t.public_sequence)));t.save(update_fields=[field])
        return Response(dict(through_sequence=getattr(t,field)))
class Summary(Private):
    def get(self,request):return Response(dict(unread_ticket_count=summary(request.user)))

class Assign(Private):
    @transaction.atomic
    def post(self,request,pk):
        old,op=duplicate(request,f'assign:{pk}');t=get_object_or_404(tickets(request.user,True).select_for_update(),pk=pk)
        demand(request.user,'assign_ticket')
        if old:return Response(ticket_data(t,request.user,True))
        revision(t,request.data);target=request.data.get('assignee_id')
        if not permit(request.user,'view_all_tickets') and (t.assignee_id is not None or target!=request.user.pk):raise PermissionDenied('只可领取未分派工单')
        if target is not None and (isinstance(target,bool) or not str(target).isdigit()):raise ValidationError('负责人标识无效')
        u=get_object_or_404(get_user_model(),pk=target,is_active=True) if target else None
        if u and not permit(u,'reply_ticket'):raise ValidationError('负责人没有回复权限')
        t.assignee=u;t.priority=request.data.get('priority',t.priority)
        if t.priority not in ['low','normal','high','urgent']:raise ValidationError('优先级无效')
        tags=request.data.get('tags',t.tags)
        if not isinstance(tags,list) or len(tags)>10 or any(not isinstance(x,str) or len(x)>30 for x in tags):raise ValidationError('标签无效')
        t.tags=tags;t.revision+=1;t.save();audit(request,'assigned',t,assignee_id=target,priority=t.priority,tags=tags)
        Operation.objects.create(**op,result_id=t.pk);return Response(ticket_data(t,request.user,True))

class Operators(Private):
    def get(self,request):
        demand(request.user,'assign_ticket')
        return Response([dict(id=u.pk,name=u.get_username()) for u in get_user_model().objects.filter(is_active=True,is_staff=True) if permit(u,'reply_ticket')])

class Redact(Private):
    @transaction.atomic
    def post(self,request,pk):
        demand(request.user,'redact_content');old,op=duplicate(request,f'redact:{pk}');t=get_object_or_404(tickets(request.user,True).select_for_update(),pk=pk)
        if old:return Response(ticket_data(t,request.user,True))
        revision(t,request.data)
        reason=short_text(request.data.get('reason'),300);m=get_object_or_404(Message,ticket=t,pk=serializers.UUIDField().run_validation(request.data.get('message_id')))
        m.redacted=True;m.body='内容已隐藏';m.save();t.revision+=1;t.save();audit(request,'redacted',t,message_id=str(m.pk),reason=reason)
        Operation.objects.create(**op,result_id=t.pk)
        return Response(ticket_data(t,request.user,True))

class Audits(Private):
    def get(self,request,pk):
        t=get_object_or_404(tickets(request.user,True),pk=pk)
        return Response(page(request,t.audit_set.order_by('-pk'),lambda a:dict(id=a.pk,actor_id=a.actor_id,action=a.action,details=a.details,created_at=a.created_at)))

class Uploads(Private):
    @transaction.atomic
    def post(self,request):
        if not permit(request.user,'reply_ticket'): formal_user(request.user)
        class Input(serializers.Serializer):
            mime=serializers.ChoiceField(choices=['image/jpeg','image/png','image/webp'])
            size=serializers.IntegerField(min_value=1,max_value=SUBMISSION_LIMITS['attachment_bytes_max'])
        s=Input(data=request.data);s.is_valid(raise_exception=True)
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        if Attachment.objects.filter(owner=request.user,message__isnull=True,created_at__gte=timezone.now()-timedelta(hours=1)).count()>=36:raise Limited()
        a=Attachment.objects.create(owner=request.user,**s.validated_data,expires_at=timezone.now()+timedelta(minutes=30))
        from diary_presets.storage import bucket
        headers={'Content-Type':a.mime,'Content-Length':str(a.size),'x-oss-forbid-overwrite':'true'}
        url=bucket().sign_url('PUT',a.key,1800,headers=headers,slash_safe=True)
        return Response(dict(id=str(a.pk),put_url=url,put_headers=headers,expires_at=a.expires_at),status=201)

class CompleteUpload(Private):
    @transaction.atomic
    def post(self,request,pk):
        a=get_object_or_404(Attachment.objects.select_for_update(),pk=pk,owner=request.user,message__isnull=True)
        if a.expires_at<=timezone.now():raise ValidationError('上传会话已过期，请重新上传')
        if a.status not in ['uploading','ready']:raise ValidationError('附件已取消')
        from diary_presets.storage import bucket
        try:
            meta=bucket().head_object(a.key)
        except Exception:
            raise ValidationError('尚未确认上传成功，请重试登记')
        if meta.content_length!=a.size or meta.headers.get('Content-Type','').split(';')[0]!=a.mime:
            raise ValidationError('截图大小或格式与上传声明不一致')
        a.status='ready';a.save(update_fields=['status']);return Response(dict(id=str(a.pk),status=a.status))
    @transaction.atomic
    def delete(self,request,pk):
        a=get_object_or_404(Attachment.objects.select_for_update(),pk=pk,owner=request.user,message__isnull=True)
        a.status='abandoned';a.save(update_fields=['status']);return Response(dict(status='abandoned'))

class AttachmentURL(Private):
    admin=False
    def get(self,request,pk):
        a=get_object_or_404(Attachment.objects.select_related('message__ticket'),pk=pk,status='ready',message__isnull=False,message__redacted=False)
        get_object_or_404(tickets(request.user,self.admin),pk=a.message.ticket_id)
        if not self.admin and a.message.visibility!='public':raise NotFound()
        if self.admin:audit(request,'attachment_viewed',a.message.ticket,attachment_id=str(pk))
        from diary_presets.storage import bucket
        return Response(dict(url=bucket().sign_url('GET',a.key,300,slash_safe=True)))

class Submission(Private):
    def get(self,request):
        key=short_text(request.query_params.get('client_request_id',''),100)
        op=Operation.objects.filter(actor=request.user,scope='create',key=key).first()
        t=tickets(request.user).filter(pk=op.result_id).first() if op else None
        return Response(dict(ticket=ticket_data(t) if t else None))

class HelpImages(Private):
    def post(self,request):
        demand(request.user,'edit_help')
        from .models import HelpImage
        class Input(serializers.Serializer):
            mime=serializers.ChoiceField(choices=['image/jpeg','image/png','image/webp'])
            size=serializers.IntegerField(min_value=1,max_value=SUBMISSION_LIMITS['attachment_bytes_max'])
        s=Input(data=request.data);s.is_valid(raise_exception=True)
        if HelpImage.objects.filter(author=request.user,created_at__gte=timezone.now()-timedelta(hours=1)).count()>=60:raise Limited()
        image=HelpImage.objects.create(author=request.user,**s.validated_data)
        from diary_presets.storage import bucket
        headers={'Content-Type':image.mime,'Content-Length':str(image.size),'x-oss-forbid-overwrite':'true'}
        return Response(dict(id=str(image.pk),put_url=bucket().sign_url('PUT',image.key,1800,headers=headers,slash_safe=True),put_headers=headers))

class HelpImageComplete(Private):
    def post(self,request,pk):
        demand(request.user,'edit_help')
        from .models import HelpImage
        image=get_object_or_404(HelpImage,pk=pk,author=request.user)
        if image.created_at<timezone.now()-timedelta(minutes=30):raise ValidationError('图片上传会话已过期')
        from diary_presets.storage import bucket
        try:meta=bucket().head_object(image.key)
        except Exception:raise ValidationError('尚未确认图片上传成功')
        if meta.content_length!=image.size or meta.headers.get('Content-Type','').split(';')[0]!=image.mime:raise ValidationError('图片大小或格式不一致')
        image.ready=True;image.save();return Response(dict(id=str(pk)))

class HelpImageURL(Public):
    admin=False
    def get(self,request,pk):
        from .models import HelpImage
        image=get_object_or_404(HelpImage,pk=pk,ready=True)
        if self.admin:demand(request.user,'edit_help')
        else:
            # Only approved/help-specific assets referenced by a live version are public-readable.
            if not any(f'support-image:{pk}' in a.published.get('body','') for a in Article.objects.filter(live=True,category__active=True) if applicable(a,request)):raise NotFound()
        from diary_presets.storage import bucket
        return Response(dict(url=bucket().sign_url('GET',image.key,300,slash_safe=True)))

class ReplyTemplates(Private):
    def get(self,request):
        demand(request.user,'reply_ticket')
        return Response(configuration().templates)
