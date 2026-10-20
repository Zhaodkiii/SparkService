import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


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
    audience = models.CharField(max_length=8, default='public', choices=[('public','Public'),('private','Private')], db_index=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='private_presets')
    customization_id = models.UUIDField(null=True, unique=True)
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=0)
    current = models.ForeignKey('Version', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    draft = models.JSONField(default=dict)

    class Meta:
        ordering = ['position', 'id']
        constraints = [models.CheckConstraint(condition=(models.Q(audience='public', owner__isnull=True, customization_id__isnull=True) | models.Q(audience='private', owner__isnull=False, customization_id__isnull=False)), name='preset_valid_audience')]


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


class ResourceTask(models.Model):
    """Single FIFO queue; Upload/Job retain their business-specific records."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.OneToOneField(Upload, null=True, blank=True, on_delete=models.CASCADE, related_name='resource_task')
    delivery_job = models.OneToOneField('diary_customizations.Job', null=True, blank=True, on_delete=models.CASCADE, related_name='resource_task')
    status = models.CharField(max_length=16, default='queued', db_index=True)
    lease = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [models.CheckConstraint(
            condition=(models.Q(upload__isnull=False, delivery_job__isnull=True) |
                       models.Q(upload__isnull=True, delivery_job__isnull=False)),
            name='resource_task_one_source')]
