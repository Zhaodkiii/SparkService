from django.db import models


class RegionDataset(models.Model):
    version = models.CharField(max_length=80, primary_key=True)
    source = models.CharField(max_length=40, default='amap')
    source_as_of = models.DateField(null=True, blank=True)
    fetched_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    content_sha256 = models.CharField(max_length=64)
    artifact_sha256 = models.CharField(max_length=64)
    artifact = models.TextField()  # Immutable canonical JSON, also exportable to CDN.
    status = models.CharField(max_length=16, default='candidate')
    counts = models.JSONField(default=dict)
    diff = models.JSONField(default=dict)


class RegionState(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    current = models.ForeignKey(RegionDataset, null=True, blank=True, on_delete=models.PROTECT)
    release_sequence = models.PositiveIntegerField(default=0)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(null=True, blank=True)
    failures = models.PositiveIntegerField(default=0)
    lock_token = models.CharField(max_length=36, blank=True)
    lock_until = models.DateTimeField(null=True, blank=True)
    budget_date = models.DateField(null=True, blank=True)
    budget_used = models.PositiveIntegerField(default=0)


class RegionSyncRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=24, default='running')
    request_count = models.PositiveIntegerField(default=0)
    dataset_version = models.CharField(max_length=80, blank=True)
    error_code = models.CharField(max_length=100, blank=True)


class RegionPublication(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    sequence = models.PositiveIntegerField(unique=True)
    dataset = models.ForeignKey(RegionDataset, on_delete=models.PROTECT)
    actor = models.CharField(max_length=120)
    reason = models.CharField(max_length=500)
