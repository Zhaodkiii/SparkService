import hashlib
import json
from datetime import timedelta
from django.db import transaction
from django.db.models import Q,F
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException,PermissionDenied,ValidationError
from backoffice.rbac import has_permission_code
from .models import Ticket,Message,Audit,Operation,Attachment

class Conflict(APIException):
    status_code=409
    default_detail='内容已更新，请刷新后重试'
class Limited(APIException):
    status_code=429
    default_detail='操作过于频繁，请稍后重试'
    wait=60

def permit(user,code):
    return bool(user and user.is_authenticated and user.is_active and (user.is_staff or user.is_superuser) and (user.is_superuser or user.has_perm('support_center.'+code) or has_permission_code(user.pk,'support_center.'+code)))
def demand(user,code):
    if not permit(user,code): raise PermissionDenied('没有此操作权限')
def tickets(user,admin=False):
    qs=Ticket.objects.select_related('owner','assignee')
    if not admin: return qs.filter(owner=user)
    demand(user,'view_ticket')
    if not permit(user,'view_all_tickets'): qs=qs.filter(Q(assignee=user)|Q(assignee__isnull=True))
    return qs

def audit(request,action,ticket=None,**details):
    return Audit.objects.create(actor=request.user if request.user.is_authenticated else None,ticket=ticket,action=action,
        details=details,request_id=str(getattr(request,'request_id',''))[:100])
def revision(obj,data):
    if data.get('revision')!=obj.revision: raise Conflict()
def short_text(value,maximum=2000,minimum=1):
    if not isinstance(value,str) or not minimum<=len(value.strip())<=maximum: raise ValidationError(f'文字长度须为 {minimum}～{maximum} 字符')
    return value.strip()
def integer(value,default=0,maximum=10000000):
    try: return max(0,min(int(value),maximum))
    except (ValueError,TypeError): return default

def duplicate(request,scope):
    # Serialize retries from the same actor before checking the unique key.
    type(request.user).objects.select_for_update().get(pk=request.user.pk)
    key=short_text(request.data.get('client_request_id',''),100)
    fingerprint=hashlib.sha256(json.dumps(request.data,sort_keys=True,default=str).encode()).hexdigest()
    old=Operation.objects.filter(actor=request.user,scope=scope,key=key).first()
    if old and old.fingerprint!=fingerprint: raise Conflict('同一请求标识不能更换内容')
    return old,dict(actor=request.user,scope=scope,key=key,fingerprint=fingerprint)

def bind(message,ids,user):
    if not isinstance(ids,list) or len(ids)>6 or len(set(str(x) for x in ids))!=len(ids): raise ValidationError('截图最多 6 张，且不能重复')
    try: ids=serializers.ListField(child=serializers.UUIDField(),max_length=6).run_validation(ids)
    except Exception: raise ValidationError('附件标识无效')
    try: assets=list(Attachment.objects.select_for_update().filter(pk__in=ids,owner=user,message__isnull=True,status='ready',expires_at__gt=timezone.now()))
    except (ValueError,TypeError): raise ValidationError('附件标识无效')
    if len(assets)!=len(ids): raise ValidationError('附件不可用、已使用或上传会话已过期')
    for a in assets: a.message=message;a.save(update_fields=['message'])

def add_message(request,ticket,body,staff=False,visibility='public',event='',attachments=None):
    public=visibility=='public'
    if public:
        ticket.public_sequence+=1;ticket.last_public_activity_at=timezone.now()
        if staff: ticket.last_staff_sequence=ticket.public_sequence
        else: ticket.last_user_sequence=ticket.public_sequence
    ticket.revision+=1;ticket.save()
    msg=Message.objects.create(ticket=ticket,author=request.user,author_type='staff' if staff else 'user',body=body,
        visibility=visibility,sequence=ticket.public_sequence if public else None,event=event)
    bind(msg,attachments or [],request.user)
    audit(request,'message' if not event else event,ticket,visibility=visibility,state=ticket.status,sequence=msg.sequence)
    if staff and public:
        from .notifications import enqueue
        enqueue(msg)
    return msg

def allowed(t,user=None,admin=False):
    if not admin:
        return [] if t.status=='closed' else ['reply','close']+(['reopen'] if t.status=='resolved' else [])
    result=[]
    if permit(user,'assign_ticket'): result+=['assign']
    if permit(user,'reply_ticket') and (t.assignee_id in (None,user.pk) or permit(user,'view_all_tickets')):
        result+=['note']
        if t.status!='closed': result+=['reply']
        if t.status=='submitted': result+=['accept']
        if t.status in ('submitted','processing','waiting_user'): result+=['request_info','resolve']
    if permit(user,'close_ticket') and t.status!='closed': result+=['close']
    if permit(user,'reopen_ticket') and t.status=='closed': result+=['reopen']
    if permit(user,'redact_content'): result+=['redact']
    return result

def ticket_data(t,user=None,admin=False):
    value=dict(id=str(t.pk),number='FB'+t.id.hex.upper(),title=t.title,kind=t.kind,status=t.status,revision=t.revision,
        public_sequence=t.public_sequence,read_sequence=t.read_sequence,unread=t.last_staff_sequence>t.read_sequence,
        last_public_activity_at=t.last_public_activity_at,created_at=t.created_at,allowed_actions=allowed(t,user,admin),
        related_type=t.related_type,related_id=str(t.related_id) if t.related_id else None)
    if admin:
        value.update(owner_id=t.owner_id,assignee_id=t.assignee_id,assignee=t.assignee.get_username() if t.assignee else '',
            priority=t.priority,tags=t.tags,environment=t.environment,source=t.source,user_unread=t.last_user_sequence>t.admin_read_sequence,
            contact=t.contact if permit(user,'view_contact') else ('***' if t.contact else ''))
    return value

def message_data(m):
    return dict(id=str(m.pk),body='内容已隐藏' if m.redacted else m.body,author_type=m.author_type,visibility=m.visibility,
        sequence=m.sequence,event=m.event,created_at=m.created_at,redacted=m.redacted,
        attachments=[] if m.redacted else [dict(id=str(a.pk),mime=a.mime,size=a.size) for a in m.attachments.filter(status='ready')])

def summary(user): return tickets(user).filter(last_staff_sequence__gt=F('read_sequence')).count()

def formal_user(user):
    from accounts.models import SocialIdentity
    if not user.is_superuser and not SocialIdentity.objects.filter(user=user).exclude(provider='device').exists():
        raise ValidationError('请先登录或绑定正式账号，以便换设备查看反馈回复')
