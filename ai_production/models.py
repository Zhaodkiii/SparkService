import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ProductionPolicy(models.Model):
    publish_key = models.UUIDField(null=True, blank=True, unique=True)
    name = models.CharField(max_length=100)
    effective_at = models.DateTimeField(default=timezone.now)
    short_limit_points = models.DecimalField(max_digits=24, decimal_places=6, default=0)
    weekly_limit_points = models.DecimalField(max_digits=24, decimal_places=6, default=0)
    rates = models.JSONField(default=dict)
    enabled = models.BooleanField(default=True)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)


class ProductionWindow(models.Model):
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=10)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    limit_points = models.DecimalField(max_digits=24, decimal_places=6, default=0)
    used_points = models.DecimalField(max_digits=24, decimal_places=6, default=0)
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
    state = models.CharField(max_length=20, default="ready")
    version = models.PositiveIntegerField(default=1)
    completed_at = models.DateTimeField(null=True)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "attempt_key"], name="production_attempt_unique"),
        ]


class ProductionCall(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    task = models.ForeignKey(ProductionTask, on_delete=models.PROTECT, related_name="calls")
    short_window = models.ForeignKey(ProductionWindow, on_delete=models.PROTECT, related_name="+")
    weekly_window = models.ForeignKey(ProductionWindow, on_delete=models.PROTECT, related_name="+")
    scene = models.CharField(max_length=64)
    model = models.CharField(max_length=200)
    category = models.CharField(max_length=16)
    input_digest = models.CharField(max_length=64)
    parameters = models.JSONField(default=dict)
    rate = models.JSONField()
    policy = models.ForeignKey(ProductionPolicy, on_delete=models.PROTECT)
    usage_due_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    execution_state = models.CharField(max_length=16, default="unknown")
    accounting_state = models.CharField(max_length=12, default="pending")
    usage_source = models.CharField(max_length=32, blank=True)
    usage = models.JSONField(default=dict)
    provider_request_id = models.CharField(max_length=200, blank=True)
    charged_points = models.DecimalField(max_digits=24, decimal_places=6, default=0)
    budget = models.DecimalField(max_digits=24, decimal_places=6)
    version = models.PositiveIntegerField(default=1)


class ProductionLedger(models.Model):
    call = models.ForeignKey(ProductionCall, on_delete=models.PROTECT, related_name="ledger")
    event_id = models.UUIDField(unique=True)
    payload_digest = models.CharField(max_length=64)
    event = models.CharField(max_length=24)
    delta_points = models.DecimalField(max_digits=24, decimal_places=6)
    resulting_points = models.DecimalField(max_digits=24, decimal_places=6)
    usage_source = models.CharField(max_length=32)
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

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
