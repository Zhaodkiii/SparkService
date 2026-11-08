import uuid
from django.conf import settings
from django.db import models


class Provider(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    host = models.CharField(max_length=253)
    enabled = models.BooleanField(default=True)


class CredentialSlot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    active_version = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)


class CredentialVersion(models.Model):
    slot = models.ForeignKey(CredentialSlot, on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    ciphertext = models.TextField()
    fingerprint = models.CharField(max_length=64)
    suffix = models.CharField(max_length=4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['slot', 'version'], name='runtime_slot_version')]


class Model(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    model_id = models.CharField(max_length=200)
    adapter_id = models.CharField(max_length=50)
    endpoint = models.URLField(max_length=500)
    capabilities = models.JSONField(default=list)
    enabled = models.BooleanField(default=True)


class Channel(models.Model):
    # One deployed environment, one iOS protocol generation; no client-selected environment.
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    draft = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=1)
    version = models.PositiveIntegerField(default=1)
    current = models.ForeignKey('Release', on_delete=models.PROTECT, null=True, related_name='+')
    enabled = models.BooleanField(default=True)
    disabled_scenes = models.JSONField(default=list)


class Release(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sequence = models.PositiveIntegerField(unique=True)
    request_key = models.UUIDField(unique=True)
    request_hash = models.CharField(max_length=64)
    snapshot = models.JSONField()
    config_hash = models.CharField(max_length=64)
    reason = models.CharField(max_length=500)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)


class Binding(models.Model):
    task = models.OneToOneField('ai_production.ProductionTask', on_delete=models.PROTECT, primary_key=True)
    release = models.ForeignKey(Release, on_delete=models.PROTECT)
    required_scenes = models.JSONField()
    capabilities = models.JSONField()


class Audit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    action = models.CharField(max_length=50)
    target = models.CharField(max_length=100, blank=True)
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class Delivery(models.Model):
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    task_id = models.UUIDField()
    release_id = models.UUIDField(null=True)
    request_id = models.UUIDField(default=uuid.uuid4)
    code = models.CharField(max_length=60)
    credential_versions = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class TestRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    snapshot = models.JSONField()
    config_hash = models.CharField(max_length=64)
    versions = models.JSONField()
    state = models.CharField(max_length=20, default='queued')
    results = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class ClientEvent(models.Model):
    event_id = models.UUIDField(primary_key=True)
    task = models.ForeignKey('ai_production.ProductionTask', on_delete=models.CASCADE)
    scene = models.CharField(max_length=60)
    code = models.CharField(max_length=60)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
