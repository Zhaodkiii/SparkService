"""Font metadata only. Resource bodies live in OSS, never in this service."""
import uuid
from django.conf import settings
from django.db import models

class FontFamily(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=120)
    active = models.BooleanField(default=False)
    featured = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    current = models.ForeignKey('FontRelease', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    first_published_at = models.DateTimeField(null=True)
    state_revision = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        permissions = [('publish_fontfamily', 'Publish fonts'), ('takedown_fontfamily', 'Change font availability'), ('upload_fontfamily', 'Upload font assets'), ('sync_fontfamily', 'Synchronize fonts to production')]

class FontDraft(models.Model):
    family = models.OneToOneField(FontFamily, primary_key=True, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField(default=1)
    base_version = models.PositiveIntegerField(default=0)
    content = models.JSONField(default=dict)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

class FontAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family = models.ForeignKey(FontFamily, on_delete=models.PROTECT)
    kind = models.CharField(max_length=16)
    object_key = models.CharField(max_length=255, unique=True)
    sha256 = models.CharField(max_length=64)
    byte_size = models.PositiveBigIntegerField()
    mime = models.CharField(max_length=80)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class FontRelease(models.Model):
    family = models.ForeignKey(FontFamily, on_delete=models.PROTECT, related_name='releases')
    number = models.PositiveIntegerField()
    content = models.JSONField(default=dict)
    digest = models.CharField(max_length=64)
    assets = models.ManyToManyField(FontAsset, related_name='releases')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['family','number'], name='font_release_number')]

class FontUpload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family = models.ForeignKey(FontFamily, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=16)
    name = models.CharField(max_length=160)
    object_key = models.CharField(max_length=1024)
    candidate_key = models.CharField(max_length=1024, blank=True)
    etag = models.CharField(max_length=200, blank=True)
    byte_size = models.PositiveBigIntegerField()
    mime = models.CharField(max_length=80)
    md5 = models.CharField(max_length=24)
    declared_sha256 = models.CharField(max_length=64)
    state = models.CharField(max_length=24, default='created', db_index=True)
    lease_token = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    attempts = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=300, blank=True)
    asset = models.ForeignKey(FontAsset, null=True, on_delete=models.PROTECT)
    expires_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

class FontPersonalEntry(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    family = models.ForeignKey(FontFamily, on_delete=models.PROTECT)
    favorite = models.BooleanField(default=False)
    acquired = models.BooleanField(default=False)
    free_claimed = models.BooleanField(default=False)
    claim_policy_revision = models.PositiveIntegerField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','family'], name='font_personal_unique')]

class FontUsageGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    document_id = models.UUIDField()
    release = models.ForeignKey(FontRelease, on_delete=models.PROTECT)
    face_id = models.CharField(max_length=80)
    source = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','document_id','release','face_id'], name='font_usage_unique')]

class FontPublishOperation(models.Model):
    family = models.ForeignKey(FontFamily, on_delete=models.PROTECT)
    key = models.CharField(max_length=100)
    digest = models.CharField(max_length=64)
    release = models.ForeignKey(FontRelease, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['family','key'], name='font_publish_unique')]

class FontAudit(models.Model):
    family = models.ForeignKey(FontFamily, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=40)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class FontSyncTask(models.Model):
    """Durable source tasks and target receipts; protocol identities never use user PKs."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    side = models.CharField(max_length=12)
    source_environment = models.CharField(max_length=80)
    library_uuid = models.UUIDField()
    source_version = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)
    snapshot = models.JSONField(default=dict)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    state = models.CharField(max_length=40, default='preflighting')
    commit_status = models.CharField(max_length=20, default='not_committed')
    result = models.JSONField(default=dict)
    baseline = models.CharField(max_length=64, blank=True)
    remote_id = models.CharField(max_length=64, blank=True)
    remote_preflight_id = models.CharField(max_length=64, blank=True)
    idempotency_key = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(null=True)
    lease_until = models.DateTimeField(null=True)
    lease_token = models.CharField(max_length=64, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['side', 'library_uuid', 'created_at'], name='font_sync_history')]


class FontSyncSlot(models.Model):
    library_uuid = models.UUIDField(primary_key=True)
    active_task = models.ForeignKey(FontSyncTask, null=True, on_delete=models.PROTECT)


class FontSyncMapping(models.Model):
    source_environment = models.CharField(max_length=80)
    library_uuid = models.UUIDField()
    source_version = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)
    target_version = models.ForeignKey(FontRelease, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['source_environment','library_uuid','source_version','content_hash'], name='font_sync_snapshot')]
