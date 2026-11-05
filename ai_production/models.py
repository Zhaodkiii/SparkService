import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ProductionPolicy(models.Model):
    publish_key = models.UUIDField(null=True, blank=True, unique=True)
    name = models.CharField(max_length=100)
    effective_at = models.DateTimeField(default=timezone.now)
    short_limit = models.PositiveIntegerField()
    weekly_limit = models.PositiveIntegerField()
    hold_hours = models.PositiveIntegerField(default=24)
    enabled = models.BooleanField(default=True)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)


class ProductionWindow(models.Model):
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=10)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    limit = models.PositiveIntegerField()
    used = models.PositiveIntegerField(default=0)
    reserved = models.PositiveIntegerField(default=0)
    policy = models.ForeignKey(ProductionPolicy, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "kind", "starts_at"], name="production_window_unique"),
        ]


class ProductionTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    attempt_key = models.UUIDField()
    input_digest = models.CharField(max_length=64)
    state = models.CharField(max_length=20, default="reserved")
    version = models.PositiveIntegerField(default=1)
    reservation_id = models.UUIDField(default=uuid.uuid4)
    short_window = models.ForeignKey(ProductionWindow, on_delete=models.PROTECT, related_name="+")
    weekly_window = models.ForeignKey(ProductionWindow, on_delete=models.PROTECT, related_name="+")
    expires_at = models.DateTimeField()
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "attempt_key"], name="production_attempt_unique"),
        ]


class ProductionLedger(models.Model):
    task = models.ForeignKey(ProductionTask, on_delete=models.PROTECT)
    reservation_id = models.UUIDField()
    event = models.CharField(max_length=20)
    short_window = models.ForeignKey(ProductionWindow, on_delete=models.PROTECT, related_name="+")
    weekly_window = models.ForeignKey(ProductionWindow, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=500, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["reservation_id", "event"], name="production_ledger_unique"),
        ]


class ProductionControl(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    accepting = models.BooleanField(default=True)
    reason = models.CharField(max_length=500, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)


class ProductionQuotaReset(models.Model):
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_key = models.UUIDField(unique=True)
    scope = models.CharField(max_length=10)
    reason = models.CharField(max_length=500)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    windows = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
