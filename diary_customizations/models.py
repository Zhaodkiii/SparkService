"""Private commissioning records. Immutable submissions and versions never follow drafts."""
import uuid
from django.conf import settings
from django.db import models

class Request(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    creation_key = models.UUIDField()
    title = models.CharField(max_length=60, blank=True)
    brief = models.JSONField(default=dict)
    status = models.CharField(max_length=24, default='draft', db_index=True)
    revision = models.PositiveIntegerField(default=1)
    resume_status = models.CharField(max_length=24, default='submitted')
    accepted_submission = models.ForeignKey('Submission', null=True, on_delete=models.PROTECT, related_name='+')
    current_delivery = models.ForeignKey('Delivery', null=True, on_delete=models.PROTECT, related_name='+')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='custom_assignments')
    due_at = models.DateTimeField(null=True)
    internal_note = models.TextField(blank=True)
    last_read_sequence = models.PositiveIntegerField(default=0)
    event_sequence = models.PositiveIntegerField(default=0)
    revision_round = models.PositiveIntegerField(default=0)
    deleted_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-updated_at', '-id']
        constraints = [models.UniqueConstraint(fields=['owner','creation_key'], name='custom_create_once')]

class Submission(models.Model):
    request = models.ForeignKey(Request, on_delete=models.PROTECT, related_name='submissions')
    number = models.PositiveIntegerField()
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['request','number'], name='custom_submission_number')]

class Asset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(Request, on_delete=models.PROTECT, related_name='assets')
    client_id = models.UUIDField()
    position = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=500, blank=True)
    must_use = models.BooleanField(default=False)
    crop_allowed = models.BooleanField(default=True)
    cover_preferred = models.BooleanField(default=False)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    mime = models.CharField(max_length=40)
    object_key = models.CharField(max_length=1024, blank=True)
    thumbnail_key = models.CharField(max_length=1024, blank=True)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=24, default='uploading')
    deleted_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['request','client_id'], name='custom_asset_once')]

class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(Request, on_delete=models.PROTECT, related_name='jobs')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    asset = models.OneToOneField(Asset, null=True, on_delete=models.PROTECT, related_name='job')
    submission = models.ForeignKey(Submission, null=True, on_delete=models.PROTECT)
    kind = models.CharField(max_length=16)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    object_key = models.CharField(max_length=1024)
    status = models.CharField(max_length=24, default='uploading', db_index=True)
    error = models.CharField(max_length=1000, blank=True)
    lease = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['request','kind','sha256','submission'], name='custom_source_once')]

class Delivery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(Request, on_delete=models.PROTECT, related_name='deliveries')
    submission = models.ForeignKey(Submission, on_delete=models.PROTECT)
    job = models.OneToOneField(Job, on_delete=models.PROTECT)
    version = models.OneToOneField('diary_presets.Version', on_delete=models.PROTECT, related_name='custom_delivery')
    number = models.PositiveIntegerField()
    published_number = models.PositiveIntegerField(null=True)
    status = models.CharField(max_length=24, default='ready_for_review')
    note = models.TextField(blank=True)
    production_map = models.JSONField(default=dict)
    delivered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    delivered_at = models.DateTimeField(null=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['request','number'], name='custom_delivery_number'),
                       models.UniqueConstraint(fields=['request','published_number'],name='custom_published_number')]

class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(Request, on_delete=models.PROTECT, related_name='events')
    sequence = models.PositiveIntegerField()
    action = models.CharField(max_length=40)
    message = models.TextField(blank=True)
    details = models.JSONField(default=dict)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='custom_events')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['sequence']
        constraints = [models.UniqueConstraint(fields=['request','sequence'], name='custom_event_sequence')]

class Operation(models.Model):
    request = models.ForeignKey(Request, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    key = models.CharField(max_length=100)
    action = models.CharField(max_length=60)
    digest = models.CharField(max_length=64)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['request','actor','key'], name='custom_operation_once')]
