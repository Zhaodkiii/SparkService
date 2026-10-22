import uuid
from django.conf import settings
from django.db import models

DEFAULT_TYPES = [dict(code=c, name=n) for c,n in [('usage','使用问题'),('suggestion','功能建议'),('error','异常报错'),('order','订单相关'),('other','其他')]]
def default_types(): return [dict(v) for v in DEFAULT_TYPES]

class Config(models.Model):
    key = models.CharField(max_length=40, primary_key=True, default='traveldiary')
    accepting = models.BooleanField(default=False)
    pause_message = models.CharField(max_length=300, default='反馈服务正在准备中，请稍后再试')
    service_hours = models.CharField(max_length=200, blank=True)
    contact = models.CharField(max_length=200, blank=True)
    types = models.JSONField(default=default_types)
    templates = models.JSONField(default=list)
    retention_days = models.PositiveIntegerField(default=180)
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        permissions = [(c,n) for c,n in [('manage_config','配置反馈服务'),('view_all_tickets','查看全部反馈'),('reply_ticket','回复反馈'),('assign_ticket','分派反馈'),('close_ticket','关闭反馈'),('reopen_ticket','重开反馈'),('view_contact','查看联系方式'),('redact_content','隐藏敏感内容'),('edit_help','编辑帮助'),('publish_help','发布帮助')]]

class Category(models.Model):
    code = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=100)
    sort = models.IntegerField(default=0)
    active = models.BooleanField(default=True)

class Article(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(Category,on_delete=models.PROTECT)
    draft = models.JSONField(default=dict)
    published = models.JSONField(default=dict)
    live = models.BooleanField(default=False)
    ever_published = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1)
    published_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

class ArticleVersion(models.Model):
    article = models.ForeignKey(Article,on_delete=models.CASCADE,related_name='versions')
    content = models.JSONField(default=dict)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Ticket(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='support_tickets')
    title = models.CharField(max_length=60)
    kind = models.CharField(max_length=60)
    status = models.CharField(max_length=30,default='submitted')
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,related_name='assigned_support_tickets')
    contact = models.CharField(max_length=100,blank=True)
    source = models.CharField(max_length=40,default='settings')
    article_id = models.UUIDField(null=True)
    previous_ticket_id = models.UUIDField(null=True)
    related_type = models.CharField(max_length=30,blank=True)
    related_id = models.UUIDField(null=True)
    environment = models.JSONField(default=dict)
    priority = models.CharField(max_length=20,default='normal')
    tags = models.JSONField(default=list)
    revision = models.PositiveIntegerField(default=1)
    public_sequence = models.PositiveIntegerField(default=0)
    read_sequence = models.PositiveIntegerField(default=0)
    admin_read_sequence = models.PositiveIntegerField(default=0)
    last_user_sequence = models.PositiveIntegerField(default=0)
    last_staff_sequence = models.PositiveIntegerField(default=0)
    last_public_activity_at = models.DateTimeField(auto_now_add=True,db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Message(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    ticket = models.ForeignKey(Ticket,on_delete=models.CASCADE,related_name='messages')
    author = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    author_type = models.CharField(max_length=15)
    body = models.TextField()
    visibility = models.CharField(max_length=15,default='public')
    sequence = models.PositiveIntegerField(null=True)
    event = models.CharField(max_length=30,blank=True)
    redacted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['ticket','sequence'],name='support_public_sequence')]

class Attachment(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    message = models.ForeignKey(Message,on_delete=models.CASCADE,null=True,related_name='attachments')
    mime = models.CharField(max_length=30)
    size = models.PositiveIntegerField()
    status = models.CharField(max_length=20,default='uploading')
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    @property
    def key(self): return f'traveldiary/support/{self.owner_id}/{self.id}'

class Operation(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='support_operations')
    scope = models.CharField(max_length=100)
    key = models.CharField(max_length=100)
    fingerprint = models.CharField(max_length=64)
    result_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['actor','scope','key'],name='support_operation_key')]

class Audit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    ticket = models.ForeignKey(Ticket,on_delete=models.CASCADE,null=True)
    action = models.CharField(max_length=60)
    details = models.JSONField(default=dict)
    request_id = models.CharField(max_length=100,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class HelpImage(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    author=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    mime=models.CharField(max_length=30)
    size=models.PositiveIntegerField()
    ready=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)
    @property
    def key(self):return f'traveldiary/support-help/{self.pk}'

class GarbageObject(models.Model):
    key=models.CharField(max_length=300,unique=True)
    created_at=models.DateTimeField(auto_now_add=True)
