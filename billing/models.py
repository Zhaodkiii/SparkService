"""Durable billing records. Only RevenueCat owns spendable balances."""
import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q

class UUIDRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        abstract = True

class BillingIdentity(UUIDRecord):
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    rc_project_id = models.CharField(max_length=64)
    rc_app_user_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    wallet_domain = models.CharField(max_length=16, choices=[('sandbox','Sandbox'),('production','Production')])
    state = models.CharField(max_length=24, default='active')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['account','rc_project_id','wallet_domain'], name='billing_identity_account_domain')]

class WalletSession(UUIDRecord):
    """Opaque server-issued binding after verified StoreKit environment evidence."""
    identity = models.ForeignKey(BillingIdentity, on_delete=models.PROTECT)
    expires_at = models.DateTimeField()
    proof_digest = models.CharField(max_length=64)

class RechargeProduct(UUIDRecord):
    rc_project_id = models.CharField(max_length=64)
    apple_product_id = models.CharField(max_length=200)
    rc_product_id = models.CharField(max_length=64)
    rc_package_id = models.CharField(max_length=64)
    units = models.PositiveIntegerField()
    currency_code = models.CharField(max_length=16, default='DIAMOND')
    configuration_revision = models.PositiveIntegerField(default=1)
    state = models.CharField(max_length=16, default='draft')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['rc_project_id','apple_product_id'], name='billing_recharge_store_product'), models.CheckConstraint(condition=Q(units__gt=0),name='billing_recharge_positive')]

class ContentOffer(UUIDRecord):
    target_kind = models.CharField(max_length=24, choices=[('template','Template'),('sticker_library','Sticker library'),('font','Font')])
    target_id = models.UUIDField()
    title = models.CharField(max_length=160)
    ownership_scope = models.CharField(max_length=32, default='personal_permanent')
    state = models.CharField(max_length=16, default='draft')
    current_policy_revision = models.ForeignKey('ContentPolicyRevision', null=True, on_delete=models.PROTECT, related_name='+')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['target_kind','target_id','ownership_scope'], name='billing_content_target_scope')]
        permissions = [('view_pricing','View billing pricing'),('change_pricing_draft','Edit billing pricing drafts'),('publish_pricing','Publish billing pricing'),('resolve_refund','Resolve billing refunds')]

class ContentPolicyRevision(UUIDRecord):
    offer = models.ForeignKey(ContentOffer,on_delete=models.PROTECT,related_name='policies')
    revision = models.PositiveIntegerField()
    access_mode = models.CharField(max_length=24,choices=[(x,x) for x in ['free','pro_only','diamond_only','pro_or_diamond']])
    diamond_price = models.PositiveIntegerField(null=True)
    currency_code = models.CharField(max_length=16,null=True)
    pro_entitlement_key = models.CharField(max_length=64,null=True)
    bundled_grants = models.JSONField(default=list)
    terms_version = models.CharField(max_length=64,default='content-personal-v1')
    content_scope_snapshot = models.JSONField(default=dict)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['offer','revision'],name='billing_policy_revision'),models.CheckConstraint(condition=(Q(access_mode__in=['free','pro_only'],diamond_price__isnull=True,currency_code__isnull=True)|Q(access_mode__in=['diamond_only','pro_or_diamond'],diamond_price__gt=0,diamond_price__isnull=False,currency_code='DIAMOND')),name='billing_policy_price_mode')]

class ContentPolicyDraft(models.Model):
    offer = models.OneToOneField(ContentOffer,on_delete=models.PROTECT,primary_key=True)
    expected_base_revision = models.PositiveIntegerField(default=0)
    body = models.JSONField(default=dict)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

class WalletGate(models.Model):
    identity = models.OneToOneField(BillingIdentity,on_delete=models.PROTECT,primary_key=True)
    state = models.CharField(max_length=32,default='ready')
    active_operation = models.ForeignKey('WalletOperation',null=True,on_delete=models.PROTECT,related_name='+')
    version = models.PositiveBigIntegerField(default=0)

class WalletSnapshot(models.Model):
    identity = models.OneToOneField(BillingIdentity,on_delete=models.PROTECT,primary_key=True)
    provider_balance = models.PositiveBigIntegerField(null=True)
    fetched_at = models.DateTimeField(null=True)
    version = models.PositiveBigIntegerField(default=0)
    sync_state = models.CharField(max_length=16,default='stale')

class MembershipSnapshot(models.Model):
    identity = models.OneToOneField(BillingIdentity,on_delete=models.PROTECT,primary_key=True)
    active_until = models.DateTimeField(null=True)
    verified_at = models.DateTimeField(null=True)
    last_event_at = models.DateTimeField(null=True)
    access_granted = models.BooleanField(default=False)
    subscription_status = models.CharField(max_length=32, default='unknown')
    auto_renewal_status = models.CharField(max_length=48, default='unknown')
    product_id = models.CharField(max_length=255, blank=True)
    period_ends_at = models.DateTimeField(null=True)
    needs_sync = models.BooleanField(default=True)

class RedemptionQuote(UUIDRecord):
    identity = models.ForeignKey(BillingIdentity,on_delete=models.PROTECT)
    offer = models.ForeignKey(ContentOffer,on_delete=models.PROTECT)
    policy_revision = models.ForeignKey(ContentPolicyRevision,on_delete=models.PROTECT)
    quoted_units = models.PositiveIntegerField()
    expires_at = models.DateTimeField()

class RedemptionOrder(UUIDRecord):
    identity = models.ForeignKey(BillingIdentity,on_delete=models.PROTECT)
    offer = models.ForeignKey(ContentOffer,on_delete=models.PROTECT)
    quote = models.ForeignKey(RedemptionQuote,on_delete=models.PROTECT)
    client_request_key = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    amount = models.PositiveIntegerField()
    status = models.CharField(max_length=32,default='prepared',db_index=True)
    last_error_code = models.CharField(max_length=64,blank=True)
    fulfilled_at = models.DateTimeField(null=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['identity','client_request_key'],name='billing_redemption_client_key')]

class WalletOperation(UUIDRecord):
    identity = models.ForeignKey(BillingIdentity,on_delete=models.PROTECT)
    order = models.ForeignKey(RedemptionOrder,null=True,on_delete=models.PROTECT,related_name='operations')
    funding = models.ForeignKey('CustomizationFunding',null=True,on_delete=models.PROTECT,related_name='operations')
    kind = models.CharField(max_length=24,choices=[('debit','Debit'),('compensation','Compensation')])
    delta = models.BigIntegerField()
    rc_idempotency_key = models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    reference = models.CharField(max_length=180)
    request_body_hash = models.CharField(max_length=64)
    state = models.CharField(max_length=24,default='prepared',db_index=True)
    attempt_count = models.PositiveIntegerField(default=0)
    first_sent_at = models.DateTimeField(null=True)
    next_attempt_at = models.DateTimeField(null=True)
    lease_token = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    response_status = models.PositiveIntegerField(null=True)
    response_body = models.JSONField(default=dict)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['order','kind'],name='billing_operation_order_kind'),models.UniqueConstraint(fields=['funding','kind'],name='billing_operation_funding_kind'),models.CheckConstraint(condition=Q(order__isnull=False,funding__isnull=True)|Q(order__isnull=True,funding__isnull=False),name='billing_operation_one_subject'),models.CheckConstraint(condition=Q(kind='debit',delta__lt=0)|Q(kind='compensation',delta__gt=0),name='billing_operation_delta_sign')]

class ContentOwnership(UUIDRecord):
    identity = models.ForeignKey(BillingIdentity,on_delete=models.PROTECT)
    target_kind = models.CharField(max_length=24)
    target_id = models.UUIDField()
    source_order = models.ForeignKey(RedemptionOrder,null=True,on_delete=models.PROTECT)
    grant_line = models.CharField(max_length=80)
    source_kind = models.CharField(max_length=24,default='diamond_redemption')
    state = models.CharField(max_length=16,default='active')
    terms_snapshot = models.JSONField(default=dict)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['source_order','grant_line'],name='billing_ownership_order_line')]

class OwnershipSlot(models.Model):
    identity = models.ForeignKey(BillingIdentity,on_delete=models.PROTECT)
    offer = models.ForeignKey(ContentOffer,on_delete=models.PROTECT)
    active_order = models.ForeignKey(RedemptionOrder,null=True,on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['identity','offer'],name='billing_ownership_slot')]

class WalletLedgerEntry(models.Model):
    identity = models.ForeignKey(BillingIdentity,on_delete=models.PROTECT)
    source_key = models.CharField(max_length=200,unique=True)
    delta = models.BigIntegerField(null=True)
    observed_balance = models.PositiveBigIntegerField(null=True)
    entry_kind = models.CharField(max_length=32)
    title = models.CharField(max_length=200)
    order = models.ForeignKey(RedemptionOrder,null=True,on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

class CurrencyEvent(models.Model):
    event_id = models.CharField(max_length=200,unique=True)
    identity = models.ForeignKey(BillingIdentity,null=True,on_delete=models.PROTECT)
    payload = models.JSONField()
    state = models.CharField(max_length=24,default='pending',db_index=True)
    received_at = models.DateTimeField(auto_now_add=True)

class ReconciliationCase(UUIDRecord):
    identity = models.ForeignKey(BillingIdentity,null=True,on_delete=models.PROTECT)
    operation = models.OneToOneField(WalletOperation,null=True,on_delete=models.PROTECT)
    kind = models.CharField(max_length=64)
    evidence = models.JSONField(default=dict)
    status = models.CharField(max_length=16,default='open')

class BillingAudit(UUIDRecord):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.PROTECT)
    action = models.CharField(max_length=64)
    target = models.CharField(max_length=100)
    detail = models.JSONField(default=dict)

class CustomizationPackage(UUIDRecord):
    code = models.CharField(max_length=64,unique=True)
    title = models.CharField(max_length=120)
    state = models.CharField(max_length=16,default='draft')
    current_revision = models.ForeignKey('CustomizationPackageRevision',null=True,on_delete=models.PROTECT,related_name='+')

class CustomizationPackageRevision(UUIDRecord):
    package = models.ForeignKey(CustomizationPackage,on_delete=models.PROTECT,related_name='revisions')
    revision = models.PositiveIntegerField()
    standard_diamonds = models.PositiveIntegerField()
    pro_diamonds = models.PositiveIntegerField(null=True)
    included_pages = models.PositiveIntegerField(default=12)
    max_photos = models.PositiveIntegerField(default=30)
    included_revision_rounds = models.PositiveIntegerField(default=1)
    lead_workdays = models.PositiveIntegerField(default=3)
    terms_version = models.CharField(max_length=64)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['package','revision'],name='billing_custom_package_revision'),models.CheckConstraint(condition=Q(standard_diamonds__gt=0)&(Q(pro_diamonds__isnull=True)|Q(pro_diamonds__gt=0,pro_diamonds__lte=models.F('standard_diamonds'))),name='billing_custom_price_valid')]

class CustomizationQuote(UUIDRecord):
    request = models.ForeignKey('diary_customizations.Request',on_delete=models.PROTECT,related_name='billing_quotes')
    package_revision = models.ForeignKey(CustomizationPackageRevision,on_delete=models.PROTECT)
    revision = models.PositiveIntegerField()
    expected_request_revision = models.PositiveIntegerField()
    standard_diamonds = models.PositiveIntegerField()
    pro_diamonds = models.PositiveIntegerField(null=True)
    scope_snapshot = models.JSONField(default=dict)
    expires_at = models.DateTimeField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['request','revision'],name='billing_custom_quote_revision')]

class CustomizationFunding(UUIDRecord):
    request = models.ForeignKey('diary_customizations.Request',on_delete=models.PROTECT,related_name='diamond_fundings')
    identity = models.ForeignKey(BillingIdentity,on_delete=models.PROTECT)
    quote = models.ForeignKey(CustomizationQuote,on_delete=models.PROTECT)
    client_request_key = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    amount = models.PositiveIntegerField()
    used_pro_price = models.BooleanField(default=False)
    status = models.CharField(max_length=24,default='prepared')
    class Meta:
        constraints=[models.UniqueConstraint(fields=['identity','client_request_key'],name='billing_custom_client_key')]

class TopUpRecord(UUIDRecord):
    identity = models.ForeignKey(BillingIdentity,on_delete=models.PROTECT)
    store = models.CharField(max_length=40)
    app_id = models.CharField(max_length=100)
    purchase_environment = models.CharField(max_length=24)
    store_transaction_id = models.TextField()
    transaction_digest = models.CharField(max_length=64)
    original_transaction_id = models.TextField(blank=True)
    recharge_product = models.ForeignKey(RechargeProduct,on_delete=models.PROTECT)
    expected_units = models.PositiveIntegerField()
    verified_units = models.IntegerField(null=True)
    state = models.CharField(max_length=24,default='purchase_observed')
    purchased_at = models.DateTimeField(null=True)
    grant_confirmed_at = models.DateTimeField(null=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['store','app_id','purchase_environment','transaction_digest'],name='billing_topup_store_transaction')]

class StorePayment(UUIDRecord):
    """Reporting projection only; never grants currency or entitlement."""
    identity = models.ForeignKey(BillingIdentity, on_delete=models.PROTECT)
    transaction_digest = models.CharField(max_length=64, unique=True)
    store_transaction_id = models.TextField()
    product_id = models.CharField(max_length=200)
    kind = models.CharField(max_length=24)
    amount = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    currency = models.CharField(max_length=3, blank=True)
    purchased_at = models.DateTimeField(null=True)
    payment_confirmed = models.BooleanField(default=False)
    refund_state = models.CharField(max_length=24, default='none')
    refund_event_at = models.DateTimeField(null=True)
    lifecycle = models.CharField(max_length=40, blank=True)
    lifecycle_at = models.DateTimeField(null=True)
    events = models.ManyToManyField(CurrencyEvent)
