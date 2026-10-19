"""印制订单保存价格、地址和生产版本快照，不跟随作品或商品后续修改。"""
import uuid
from django.utils import timezone
from django.conf import settings
from django.db import models


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=120)
    active = models.BooleanField(default=False)
    proof_approved = models.BooleanField(default=False)
    proof_note = models.TextField(blank=True)
    proof_at = models.DateTimeField(null=True)
    proof_by = models.CharField(max_length=150, blank=True)
    revision = models.PositiveIntegerField(default=1)
    width_mm = models.PositiveIntegerField(default=148)
    height_mm = models.PositiveIntegerField(default=210)
    paper = models.CharField(max_length=120)
    binding = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    # 首期支持无出血的独立封面+按序内页，禁止未实现工艺上线。
    cover_mode = models.CharField(max_length=32, default='separate_front_back')
    duplex = models.BooleanField(default=True)
    min_pages = models.PositiveIntegerField(default=2)
    max_pages = models.PositiveIntegerField(default=200)
    max_quantity = models.PositiveIntegerField(default=10)
    free_printing = models.BooleanField(default=False)
    base_fen = models.PositiveIntegerField(default=0)
    page_fen = models.PositiveIntegerField(default=0)
    shipping_fen = models.PositiveIntegerField(default=0)
    regions = models.JSONField(default=list)
    lead_time = models.CharField(max_length=200, blank=True)
    terms = models.TextField(blank=True)


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    creation_key = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    title = models.CharField(max_length=120)
    spec = models.JSONField()
    address = models.JSONField()
    snapshot = models.JSONField()
    quantity = models.PositiveIntegerField()
    page_count = models.PositiveIntegerField()
    total_fen = models.PositiveIntegerField()
    file_state = models.CharField(max_length=24, default='uploading')
    payment_state = models.CharField(max_length=24, default='unpaid')
    state = models.CharField(max_length=24, default='draft')
    revision = models.PositiveIntegerField(default=1)
    current_production = models.ForeignKey('Production', null=True, on_delete=models.PROTECT, related_name='+')
    prepay_id = models.CharField(max_length=100, blank=True)
    transaction_id = models.CharField(max_length=100, null=True, unique=True)
    payment_started = models.BooleanField(default=False)
    cancel_requested = models.BooleanField(default=False)
    payment_expires_at = models.DateTimeField(null=True)
    refund_state = models.CharField(max_length=24, blank=True)
    refund_reason = models.CharField(max_length=200, blank=True)
    paused_from = models.CharField(max_length=24, blank=True)
    exception_reason = models.TextField(blank=True)
    after_sale_state = models.CharField(max_length=24, blank=True)
    after_sale_message = models.TextField(blank=True)
    after_sale_resolution = models.TextField(blank=True)
    stage_started_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'creation_key'], name='print_order_create_once')]
        ordering = ['-created_at', '-id']
        permissions = [('download_order', 'Download print production files'), ('refund_order', 'Refund print order')]


class Production(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='productions')
    number = models.PositiveIntegerField(default=1)
    manifest = models.JSONField()
    uploads = models.JSONField(default=dict)
    confirmed_hash = models.CharField(max_length=64)
    confirmed_at = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=24, default='uploading')
    result = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    lease = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['order', 'number'], name='print_production_number')]


class Event(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="print_events")
    action = models.CharField(max_length=40)
    details = models.JSONField(default=dict)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Shipment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='shipments')
    carrier = models.CharField(max_length=80)
    tracking_number = models.CharField(max_length=80)
    kind = models.CharField(max_length=24, default='initial')
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Receipt(models.Model):
    """事务性动作幂等收据；同一键不同负载不复用。"""
    order = models.ForeignKey(Order, on_delete=models.PROTECT)
    key = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['order', 'key'], name='print_action_once')]


class FileCleanup(models.Model):
    """被替换稿件的删除队列，不提供历史稿件读取入口。"""
    keys = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    last_error = models.CharField(max_length=120, blank=True)
