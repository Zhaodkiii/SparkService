import uuid
from django.conf import settings
from django.db import models


class Series(models.Model):
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=120)
    position = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['position', 'id']


class Template(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    series = models.ForeignKey(Series, on_delete=models.PROTECT, related_name='templates')
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=0)
    current = models.ForeignKey('Version', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    draft = models.JSONField(default=dict)

    class Meta:
        ordering = ['position', 'id']


class Version(models.Model):
    template = models.ForeignKey(Template, on_delete=models.PROTECT, related_name='versions')
    number = models.PositiveIntegerField()
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['template', 'number'], name='preset_unique_version')]


class Upload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(Template, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField()
    mode = models.CharField(max_length=8, default='book')
    after_page = models.CharField(max_length=200, blank=True)
    object_key = models.CharField(max_length=1024)
    size = models.PositiveBigIntegerField()
    status = models.CharField(max_length=24, default='uploading')
    error = models.TextField(blank=True)
    result = models.JSONField(default=dict)
    lease = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class DownloadPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    version = models.ForeignKey(Version, on_delete=models.PROTECT)
    snapshot = models.JSONField()
    expires_at = models.DateTimeField()


class Event(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    template = models.ForeignKey(Template, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
