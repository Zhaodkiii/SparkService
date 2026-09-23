from django.conf import settings
from django.db import models


class RevenueCatCustomerIdentity(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="revenuecat_identity")
    app_user_id = models.CharField(max_length=100, unique=True, db_index=True)
    last_sync_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_successful_sync_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_sync_error_code = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "RevenueCat 用户身份"
        verbose_name_plural = "RevenueCat 用户身份"


class RevenueCatCustomerAlias(models.Model):
    class Source(models.TextChoices):
        LOGIN_RESULT = "login_result", "登录结果"
        WEBHOOK = "webhook", "Webhook"
        SERVER_SYNC = "server_sync", "服务端同步"

    identity = models.ForeignKey(RevenueCatCustomerIdentity, on_delete=models.CASCADE, related_name="aliases")
    # MySQL utf8mb4 unique indexes cannot safely cover 1500 characters.
    # Look Health uses numeric App User IDs and RevenueCat anonymous aliases, both
    # far below this bound; untrusted oversized webhook aliases stay in payload.
    alias = models.CharField(max_length=255, unique=True, db_index=True)
    source = models.CharField(max_length=32, choices=Source.choices)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "RevenueCat 用户别名"
        verbose_name_plural = "RevenueCat 用户别名"


class RevenueCatEntitlement(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "有效"
        EXPIRED = "expired", "已过期"
        REVOKED = "revoked", "已撤销"
        UNKNOWN = "unknown", "未知"

    class Environment(models.TextChoices):
        PRODUCTION = "production", "生产"
        SANDBOX = "sandbox", "沙盒"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="revenuecat_entitlements")
    entitlement_identifier = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UNKNOWN, db_index=True)
    environment = models.CharField(max_length=16, choices=Environment.choices, db_index=True)
    product_id = models.CharField(max_length=255, blank=True, default="")
    store = models.CharField(max_length=32, blank=True, default="")
    period_type = models.CharField(max_length=32, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    will_renew = models.BooleanField(default=False)
    original_transaction_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    billing_status = models.CharField(max_length=32, blank=True, default="normal", db_index=True)
    unsubscribe_detected_at = models.DateTimeField(null=True, blank=True)
    billing_issue_detected_at = models.DateTimeField(null=True, blank=True)
    grace_period_expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    pending_product_id = models.CharField(max_length=255, blank=True, default="")
    product_change_effective_at = models.DateTimeField(null=True, blank=True)
    ownership_type = models.CharField(max_length=32, blank=True, default="unknown")
    last_event_type = models.CharField(max_length=64, blank=True, default="")
    last_event_timestamp_ms = models.BigIntegerField(default=0, db_index=True)
    provider_updated_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "entitlement_identifier", "environment"],
                name="subscriptions_unique_rc_entitlement_snapshot",
            )
        ]
        indexes = [models.Index(fields=["user", "environment", "status", "expires_at"], name="subscriptio_user_id_771260_idx")]
        verbose_name = "RevenueCat 权益快照"
        verbose_name_plural = "RevenueCat 权益快照"


class RevenueCatWebhookEvent(models.Model):
    class ProcessStatus(models.TextChoices):
        RECEIVED = "received", "已接收"
        PROCESSING = "processing", "处理中"
        PROCESSED = "processed", "已处理"
        UNMATCHED = "unmatched", "待匹配"
        RETRYABLE = "retryable", "待重试"
        OWNERSHIP_CONFLICT = "ownership_conflict", "归属冲突"
        FAILED = "failed", "失败"

    event_id = models.CharField(max_length=128, unique=True, db_index=True)
    event_type = models.CharField(max_length=64, blank=True, default="")
    app_user_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    environment = models.CharField(max_length=16, blank=True, default="", db_index=True)
    event_timestamp_ms = models.BigIntegerField(default=0)
    payload = models.JSONField()
    process_status = models.CharField(max_length=32, choices=ProcessStatus.choices, default=ProcessStatus.RECEIVED, db_index=True)
    matched_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="revenuecat_webhook_events")
    attempt_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["process_status", "next_retry_at", "received_at"], name="subscriptio_process_024c30_idx")]
        verbose_name = "RevenueCat Webhook 事件"
        verbose_name_plural = "RevenueCat Webhook 事件"


class RevenueCatSubscriptionOwnership(models.Model):
    class State(models.TextChoices):
        ACTIVE = "active", "有效归属"
        TOMBSTONE = "tombstone", "注销墓碑"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revenuecat_subscription_ownerships",
    )
    store = models.CharField(max_length=32)
    environment = models.CharField(max_length=16, db_index=True)
    original_transaction_id = models.CharField(max_length=255)
    state = models.CharField(max_length=16, choices=State.choices, default=State.ACTIVE, db_index=True)
    owner_account_fingerprint = models.CharField(max_length=128)
    first_product_id = models.CharField(max_length=255, blank=True, default="")
    first_bound_at = models.DateTimeField()
    last_verified_at = models.DateTimeField()
    tombstoned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["store", "environment", "original_transaction_id"],
                name="subscriptions_unique_rc_transaction_owner",
            )
        ]
        indexes = [
            models.Index(fields=["user", "environment", "state"], name="subscriptio_owner_user_env_idx"),
            models.Index(fields=["state", "tombstoned_at"], name="subscriptio_owner_state_idx"),
        ]
        verbose_name = "RevenueCat 订阅所有权"
        verbose_name_plural = "RevenueCat 订阅所有权"


class RevenueCatOwnershipConflictEvent(models.Model):
    ownership = models.ForeignKey(RevenueCatSubscriptionOwnership, on_delete=models.PROTECT, related_name="conflicts")
    attempted_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    trigger = models.CharField(max_length=32)
    store = models.CharField(max_length=32, blank=True, default="")
    environment = models.CharField(max_length=16, blank=True, default="")
    transaction_suffix = models.CharField(max_length=12, blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default="")
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["attempted_user", "occurred_at"], name="subscriptio_conflict_user_idx")]
        verbose_name = "RevenueCat 订阅归属冲突"
        verbose_name_plural = "RevenueCat 订阅归属冲突"


class RevenueCatSyncRequest(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="revenuecat_sync_requests")
    idempotency_key = models.CharField(max_length=128)
    status = models.CharField(max_length=16, default="processing")
    response_payload = models.JSONField(null=True, blank=True)
    response_status = models.PositiveSmallIntegerField(default=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "idempotency_key"], name="subscriptions_unique_sync_request_key"),
        ]
        indexes = [models.Index(fields=["user", "created_at"], name="subscriptio_sync_user_idx")]
