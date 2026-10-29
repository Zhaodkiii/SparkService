import uuid
from django.conf import settings
from django.db import models


class ResourceBlob(models.Model):
    sha256 = models.CharField(max_length=64, primary_key=True)
    object_key = models.CharField(max_length=1024)
    byte_size = models.PositiveBigIntegerField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    mime = models.CharField(max_length=40)


class Material(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_identity = models.CharField(max_length=240, unique=True)
    material_type = models.CharField(max_length=16, choices=[('sticker', '贴纸'), ('background', '背景')])
    active = models.BooleanField(default=True)


class MaterialRevision(models.Model):
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='revisions')
    digest = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=32)
    subcategory = models.CharField(max_length=32)
    keywords = models.JSONField(default=list)
    aliases = models.JSONField(default=list)
    resource = models.ForeignKey(ResourceBlob, on_delete=models.PROTECT, related_name='+')
    thumbnail = models.ForeignKey(ResourceBlob, on_delete=models.PROTECT, related_name='+')
    sources = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['material', 'digest'], name='material_revision_digest')]


class MaterialLibrary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey('diary_presets.Template', null=True, blank=True, on_delete=models.PROTECT, related_name='material_libraries')
    library_type = models.CharField(max_length=16, choices=[('sticker', '贴纸'), ('background', '背景')])
    title = models.CharField(max_length=120)
    active = models.BooleanField(default=True)
    current = models.ForeignKey('LibraryVersion', null=True, on_delete=models.PROTECT, related_name='+')

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deletion_reason = models.CharField(max_length=300, blank=True)

    first_published_at = models.DateTimeField(null=True, blank=True)
    featured = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    new_until = models.DateTimeField(null=True, blank=True)
    state_revision = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['template', 'library_type'], name='template_library_type')]
        permissions = [('publish_materiallibrary','Can publish material libraries'),('takedown_materiallibrary','Can change material availability'),('sync_materiallibrary','Can synchronize material libraries to production')]


class LibraryVersion(models.Model):
    library = models.ForeignKey(MaterialLibrary, on_delete=models.PROTECT, related_name='versions')
    number = models.PositiveIntegerField()
    preset_version = models.ForeignKey('diary_presets.Version', null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    content = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['library', 'number'], name='library_version_number')]


class LibraryItem(models.Model):
    version = models.ForeignKey(LibraryVersion, on_delete=models.CASCADE, related_name='items')
    revision = models.ForeignKey(MaterialRevision, on_delete=models.PROTECT)
    material = models.ForeignKey(Material, on_delete=models.PROTECT)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']
        constraints = [models.UniqueConstraint(fields=['version', 'material'], name='library_unique_material')]


class LibraryFavorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    library = models.ForeignKey(MaterialLibrary, on_delete=models.CASCADE, related_name='favorites')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'library'], name='user_library_favorite')]


class MaterialFavorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='favorites')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'material'], name='user_material_favorite')]


class LibraryDraft(models.Model):
    library = models.OneToOneField(MaterialLibrary, on_delete=models.CASCADE, related_name='draft')
    revision = models.PositiveIntegerField(default=1)
    base_version = models.PositiveIntegerField(default=0)
    content = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)


class MaterialUpload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=16)
    name = models.CharField(max_length=120)
    object_key = models.CharField(max_length=1024)
    byte_size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    upload_metadata = models.JSONField(default=dict)
    staging_cleaned_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=16, default='created')
    error = models.CharField(max_length=300, blank=True)
    expires_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)
    resource = models.ForeignKey(ResourceBlob, null=True, on_delete=models.PROTECT, related_name='+')
    thumbnail = models.ForeignKey(ResourceBlob, null=True, on_delete=models.PROTECT, related_name='+')


class MaterialAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    library = models.ForeignKey(MaterialLibrary, null=True, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class MaterialPublishJob(models.Model):
    library = models.ForeignKey(MaterialLibrary, on_delete=models.PROTECT)
    key = models.CharField(max_length=100)
    digest = models.CharField(max_length=64)
    version = models.ForeignKey(LibraryVersion, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['library', 'key'], name='material_publish_key')]


class TemplateLibraryBinding(models.Model):
    preset_version = models.ForeignKey('diary_presets.Version', on_delete=models.PROTECT, related_name='material_bindings')
    library_type = models.CharField(max_length=16)
    library_version = models.ForeignKey(LibraryVersion, on_delete=models.PROTECT, related_name='template_bindings')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['preset_version','library_type'],name='preset_material_binding')]


class MaterialCategory(models.Model):
    kind = models.CharField(max_length=32)
    subcategory = models.CharField(max_length=32)
    title = models.CharField(max_length=60)
    active = models.BooleanField(default=True)
    position = models.IntegerField(default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['kind','subcategory'],name='material_category_key')]


class MaterialTag(models.Model):
    title = models.CharField(max_length=30, unique=True)
    active = models.BooleanField(default=True)


class MaterialSyncTask(models.Model):
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
        indexes = [models.Index(fields=['side', 'library_uuid', 'created_at'], name='material_sync_history')]


class MaterialSyncSlot(models.Model):
    library_uuid = models.UUIDField(primary_key=True)
    active_task = models.ForeignKey(MaterialSyncTask, null=True, on_delete=models.PROTECT)


class MaterialSyncMapping(models.Model):
    source_environment = models.CharField(max_length=80)
    library_uuid = models.UUIDField()
    source_version = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)
    target_version = models.ForeignKey(LibraryVersion, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['source_environment','library_uuid','source_version','content_hash'], name='material_sync_snapshot')]


class MaterialSyncNonce(models.Model):
    digest = models.CharField(max_length=64, primary_key=True)
    expires_at = models.DateTimeField()


class TemplateMaterialLink(models.Model):
    """Editable next-publication configuration; published bindings stay immutable."""
    template = models.ForeignKey('diary_presets.Template', on_delete=models.PROTECT, related_name='material_links')
    library_type = models.CharField(max_length=16)
    library = models.ForeignKey(MaterialLibrary, null=True, on_delete=models.PROTECT, related_name='book_links')
    library_version = models.ForeignKey(LibraryVersion, null=True, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['template', 'library_type'], name='template_material_link_unique')]


class MaterialCleanupJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    state = models.CharField(max_length=16, default='preview')
    entries = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
