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
    cover_mode = models.CharField(max_length=32, default='optional_shell')
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


class PaymentChannel(models.Model):
    code = models.CharField(max_length=16, primary_key=True, choices=[('wechat','微信支付'),('alipay','支付宝')])
    enabled = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)
    revision = models.PositiveIntegerField(default=1)
    current = models.ForeignKey('PaymentConfig', null=True, blank=True, on_delete=models.PROTECT, related_name='+')


class PaymentConfig(models.Model):
    channel = models.ForeignKey(PaymentChannel, on_delete=models.PROTECT, related_name='versions')
    environment = models.CharField(max_length=16, default='production')
    public = models.JSONField(default=dict)
    encrypted = models.TextField()
    checked_at = models.DateTimeField(null=True)
    verified_note = models.TextField(blank=True)
    actor = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)


class PaymentAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='payments')
    config = models.ForeignKey(PaymentConfig, on_delete=models.PROTECT)
    key = models.UUIDField()
    amount = models.PositiveIntegerField()
    state = models.CharField(max_length=24, default='creating')
    active_slot = models.PositiveSmallIntegerField(null=True, default=1)
    provider_id = models.CharField(max_length=100, null=True)
    prepay_id = models.CharField(max_length=200, blank=True)
    expires_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True)
    lease_until = models.DateTimeField(null=True)
    checked_at = models.DateTimeField(null=True)
    failure_count = models.PositiveIntegerField(default=0)
    next_check_at = models.DateTimeField(null=True)
    last_error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['order','key'], name='print_payment_key'),
                       models.UniqueConstraint(fields=['order','active_slot'], name='print_payment_active')]
        permissions = [('query_payment', 'Query payment channel results')]


class PaymentRefund(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.OneToOneField(PaymentAttempt, on_delete=models.PROTECT, related_name='refund')
    amount = models.PositiveIntegerField()
    reason = models.CharField(max_length=200)
    state = models.CharField(max_length=24, default='pending')
    provider_id = models.CharField(max_length=100, blank=True)
    last_error = models.CharField(max_length=200, blank=True)
    lease_until = models.DateTimeField(null=True)
    checked_at = models.DateTimeField(null=True)
    failure_count = models.PositiveIntegerField(default=0)
    next_check_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=100, blank=True)
    error_category = models.CharField(max_length=24, blank=True)
    recovery_action = models.CharField(max_length=240, blank=True)
    retry_mode = models.CharField(max_length=16, default='auto')
    submission_started = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PaymentAudit(models.Model):
    actor = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=40)
    reference = models.CharField(max_length=100)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class PaymentProbe(models.Model):
    """Isolated one-cent APP integration test; never enters order fulfillment."""
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    config=models.ForeignKey(PaymentConfig,on_delete=models.PROTECT,related_name='probes')
    token=models.UUIDField(default=uuid.uuid4,editable=False)
    actor=models.CharField(max_length=150)
    amount=models.PositiveIntegerField(default=1)
    state=models.CharField(max_length=24,default='created')
    provider_id=models.CharField(max_length=100,blank=True)
    prepay_id=models.CharField(max_length=200,blank=True)
    refund_id=models.UUIDField(default=uuid.uuid4,editable=False)
    refund_state=models.CharField(max_length=24,default='pending')
    expires_at=models.DateTimeField()
    lease_until=models.DateTimeField(null=True)
    last_error=models.CharField(max_length=200,blank=True)
    close_kind=models.CharField(max_length=24,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

    @property
    def order(self):
        from types import SimpleNamespace
        return SimpleNamespace(title='管理员支付联调（自动原路退款）')
