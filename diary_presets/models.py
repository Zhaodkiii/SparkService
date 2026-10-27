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


class SearchTaxon(models.Model):
    id = models.CharField(primary_key=True, max_length=120)
    dimension = models.CharField(max_length=12, choices=[(v, v) for v in ('location', 'theme', 'style', 'usage')])
    name = models.CharField(max_length=120)
    aliases = models.JSONField(default=list)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)
    active = models.BooleanField(default=True)
    merged_into = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='merged_terms')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['dimension', 'name'], name='preset_taxon_unique_name')]


class SearchState(models.Model):
    id = models.PositiveIntegerField(primary_key=True, default=1)
    revision = models.PositiveIntegerField(default=1)


class CatalogEntry(models.Model):
    version = models.ForeignKey('Version', on_delete=models.CASCADE, related_name='search_entries')
    entity_type = models.CharField(max_length=8, db_index=True)
    entity_id = models.CharField(max_length=200)
    position = models.PositiveIntegerField(default=0)
    document = models.JSONField(default=dict)
    search_text = models.TextField(default='', blank=True)
    title_text = models.CharField(max_length=200, default='', blank=True, db_index=True)
    page_text = models.TextField(default='', blank=True)
    keyword_text = models.TextField(default='', blank=True)
    child_text = models.TextField(default='', blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['version', 'entity_type', 'entity_id'], name='preset_entry_unique')]


class CatalogEntryTerm(models.Model):
    entry = models.ForeignKey(CatalogEntry, on_delete=models.CASCADE, related_name='indexed_terms')
    taxon = models.ForeignKey(SearchTaxon, on_delete=models.PROTECT)
    dimension = models.CharField(max_length=12)
    rank = models.PositiveSmallIntegerField(default=5)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['entry', 'taxon'], name='preset_entry_taxon_unique')]
        indexes = [models.Index(fields=['dimension', 'taxon', 'entry'], name='preset_term_lookup')]


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


class PresetStatisticsState(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    started_at = models.DateTimeField(default=timezone.now)


class PresetImportEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    operation_id = models.UUIDField()
    template = models.ForeignKey(Template, on_delete=models.PROTECT, related_name='import_events')
    version = models.ForeignKey(Version, on_delete=models.PROTECT)
    mode = models.CharField(max_length=12, choices=[('book', 'Book'), ('selection', 'Selection')])
    target_book_id = models.UUIDField()
    completed_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    payload_digest = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'operation_id'], name='preset_import_operation_unique'),
            models.CheckConstraint(condition=models.Q(mode__in=['book', 'selection']), name='preset_import_valid_mode'),
        ]
        indexes = [models.Index(fields=['template', 'mode', 'received_at'], name='preset_import_stats')]


class PresetImportItem(models.Model):
    event = models.ForeignKey(PresetImportEvent, on_delete=models.CASCADE, related_name='items')
    source_page_id = models.CharField(max_length=200)
    target_page_id = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['event', 'source_page_id'], name='preset_import_source_unique'),
            models.UniqueConstraint(fields=['event', 'target_page_id'], name='preset_import_target_unique'),
        ]
