from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class NotificationTopic(models.Model):
    class Category(models.TextChoices):
        TRANSACTIONAL = "transactional", "事务性"
        SECURITY = "security", "安全"
        OPERATIONAL = "operational", "运营"
        SYSTEM = "system", "系统"
        MARKETING = "marketing", "营销"

    key = models.CharField(max_length=128, unique=True, db_index=True)
    name = models.CharField(max_length=128)
    category = models.CharField(max_length=32, choices=Category.choices, db_index=True)
    requires_user = models.BooleanField(default=False, db_index=True)
    default_channels = models.JSONField(default=list, blank=True)
    default_route_policy = models.JSONField(default=dict, blank=True)
    default_priority = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "default_priority", "id"]

    def __str__(self) -> str:
        return f"{self.key}:{self.name}"


class NotificationBusinessScene(models.Model):
    class Category(models.TextChoices):
        SECURITY = "security", "安全"
        TRANSACTIONAL = "transactional", "事务性"
        SYSTEM = "system", "系统"
        OPERATIONAL = "operational", "运营"
        MARKETING = "marketing", "营销"

    class Severity(models.TextChoices):
        INFO = "info", "信息"
        SUCCESS = "success", "成功"
        WARNING = "warning", "警告"
        CRITICAL = "critical", "严重"

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        ACTIVE = "active", "启用"
        DEPRECATED = "deprecated", "已弃用"
        RETIRED = "retired", "已退役"

    key = models.CharField(max_length=128, unique=True, db_index=True)
    domain = models.CharField(max_length=32, db_index=True)
    business_type = models.CharField(max_length=64, db_index=True)
    event_name = models.CharField(max_length=64, db_index=True)
    display_name = models.CharField(max_length=128)
    description = models.CharField(max_length=500, blank=True, default="")
    topic = models.ForeignKey(
        NotificationTopic,
        null=True,
        blank=True,
        related_name="business_scenes",
        on_delete=models.SET_NULL,
    )
    category = models.CharField(max_length=32, choices=Category.choices, db_index=True)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.INFO, db_index=True)
    default_template_key = models.CharField(max_length=128, blank=True, default="")
    default_routing = models.JSONField(default=dict, blank=True)
    variable_schema = models.JSONField(default=dict, blank=True)
    reference_schema = models.JSONField(default=dict, blank=True)
    client_action_schema = models.JSONField(default=dict, blank=True)
    idempotency_strategy = models.CharField(max_length=32, default="event", db_index=True)
    dedupe_window_seconds = models.PositiveIntegerField(default=0)
    preference_policy = models.CharField(max_length=32, default="opt_out", db_index=True)
    quiet_hour_policy = models.CharField(max_length=32, default="respect", db_index=True)
    retention_days = models.PositiveIntegerField(default=30)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    contract_version = models.PositiveIntegerField(default=1)
    owner_team = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["domain", "business_type", "event_name", "id"]
        indexes = [
            models.Index(fields=["domain", "status"]),
            models.Index(fields=["business_type", "status"]),
            models.Index(fields=["category", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.key}:{self.display_name}"

    def clean(self) -> None:
        super().clean()
        import re

        if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){2,4}", self.key or ""):
            raise ValidationError({"key": "场景编码必须为 3~5 段小写点分格式。"})
        parts = self.key.split(".")
        expected_type = ".".join(parts[:2])
        errors = {}
        if self.domain != parts[0]:
            errors["domain"] = "业务域必须等于场景编码第一段。"
        if self.business_type != expected_type:
            errors["business_type"] = "业务类型必须等于场景编码前两段。"
        if self.event_name != parts[-1]:
            errors["event_name"] = "事件名称必须等于场景编码最后一段。"
        if self.contract_version < 1:
            errors["contract_version"] = "契约版本必须大于等于 1。"
        if errors:
            raise ValidationError(errors)


class NotificationTemplate(models.Model):
    key = models.CharField(max_length=128, unique=True, db_index=True)
    name = models.CharField(max_length=128, db_index=True)
    description = models.CharField(max_length=255, blank=True, default="")
    topic_key = models.CharField(max_length=128, db_index=True, blank=True, default="")
    title_template = models.CharField(max_length=255, blank=True, default="")
    body_template = models.TextField(blank=True, default="")
    payload_template = models.JSONField(default=dict, blank=True)
    default_channels = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="notification_templates_created",
        on_delete=models.SET_NULL,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="notification_templates_updated",
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "-updated_at"]),
            models.Index(fields=["topic_key", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"notification_template:{self.id}:{self.name}"


class NotificationTemplateVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        REVIEW = "review", "审核中"
        PUBLISHED = "published", "已发布"
        RETIRED = "retired", "已下线"

    template = models.ForeignKey(NotificationTemplate, related_name="versions", on_delete=models.CASCADE)
    version = models.PositiveIntegerField(default=1)
    locale = models.CharField(max_length=32, default="zh-CN", db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    title_template = models.CharField(max_length=255, blank=True, default="")
    body_template = models.TextField(blank=True, default="")
    payload_template = models.JSONField(default=dict, blank=True)
    payload_schema = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="notification_template_versions_created",
        on_delete=models.SET_NULL,
    )
    published_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["template", "version", "locale"], name="uniq_notification_template_version_locale"),
        ]
        indexes = [
            models.Index(fields=["template", "status", "-version"]),
        ]


class ChannelTemplateVersion(models.Model):
    class Channel(models.TextChoices):
        APNS = "apns", "APNs"
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"
        WEB_PUSH = "web_push", "Web Push"
        IN_APP = "in_app", "站内信"

    template_version = models.ForeignKey(NotificationTemplateVersion, related_name="channel_versions", on_delete=models.CASCADE)
    channel = models.CharField(max_length=32, choices=Channel.choices, db_index=True)
    provider = models.CharField(max_length=64, blank=True, default="")
    provider_template_code = models.CharField(max_length=128, blank=True, default="")
    sign_name = models.CharField(max_length=128, blank=True, default="")
    content_snapshot_masked = models.TextField(blank=True, default="")
    config = models.JSONField(default=dict, blank=True)
    provider_approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["template_version", "channel", "provider"], name="uniq_channel_template_version_provider"),
        ]


class NotificationIntent(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "已创建"
        DISPATCHED = "dispatched", "已分发"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失败"
        CANCELLED = "cancelled", "已取消"
        EXPIRED = "expired", "已过期"

    topic_key = models.CharField(max_length=128, db_index=True)
    business_scene = models.CharField(max_length=128, blank=True, default="", db_index=True)
    business_domain = models.CharField(max_length=32, blank=True, default="", db_index=True)
    business_type = models.CharField(max_length=128, blank=True, default="", db_index=True)
    business_reference_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    business_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    subject_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    subject_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    template_key = models.CharField(max_length=128, blank=True, default="", db_index=True)
    template_version = models.ForeignKey(
        NotificationTemplateVersion,
        null=True,
        blank=True,
        related_name="intents",
        on_delete=models.SET_NULL,
    )
    routing = models.JSONField(default=dict, blank=True)
    sensitive_context_ciphertext = models.TextField(blank=True, default="")
    scene_contract_version = models.PositiveIntegerField(default=1)
    scene_snapshot = models.JSONField(default=dict, blank=True)
    event_id = models.CharField(max_length=64, unique=True, db_index=True, null=True, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True, db_index=True)
    actor_type = models.CharField(max_length=32, blank=True, default="", db_index=True)
    actor_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    idempotency_key = models.CharField(max_length=255, unique=True, db_index=True)
    trace_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    source = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED, db_index=True)
    priority = models.PositiveIntegerField(default=100)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["business_scene", "-created_at"]),
            models.Index(fields=["business_domain", "-created_at"]),
            models.Index(fields=["business_type", "-created_at"]),
            models.Index(fields=["business_reference_type", "business_id", "-created_at"]),
            models.Index(fields=["actor_type", "actor_id", "-created_at"]),
            models.Index(fields=["subject_type", "subject_id", "-created_at"]),
        ]


class NotificationCampaign(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "待发送"
        SCHEDULED = "scheduled", "定时中"
        RUNNING = "running", "发送中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失败"
        CANCELLED = "cancelled", "已取消"

    name = models.CharField(max_length=128, blank=True, default="", db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    channels = models.JSONField(default=list, blank=True)
    title = models.CharField(max_length=255, blank=True, default="")
    body = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    target_user_ids = models.JSONField(default=list, blank=True)
    target_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    template = models.ForeignKey(NotificationTemplate, null=True, blank=True, related_name="campaigns", on_delete=models.SET_NULL)
    intent = models.ForeignKey(NotificationIntent, null=True, blank=True, related_name="campaigns", on_delete=models.SET_NULL)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="notification_center_campaigns",
        on_delete=models.SET_NULL,
    )
    task_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]


class AudienceDefinition(models.Model):
    campaign = models.OneToOneField(NotificationCampaign, related_name="audience_definition", on_delete=models.CASCADE)
    source_type = models.CharField(max_length=32, default="explicit", db_index=True)
    criteria = models.JSONField(default=dict, blank=True)
    version = models.PositiveIntegerField(default=1)
    frozen_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AudienceSnapshot(models.Model):
    class Status(models.TextChoices):
        INCLUDED = "included", "已纳入"
        EXCLUDED = "excluded", "已排除"

    campaign = models.ForeignKey(NotificationCampaign, related_name="audience_snapshots", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="notification_audience_snapshots", on_delete=models.SET_NULL)
    recipient_type = models.CharField(max_length=16, default="user", db_index=True)
    recipient_key = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.INCLUDED, db_index=True)
    exclusion_reason = models.CharField(max_length=128, blank=True, default="")
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["campaign", "recipient_type", "recipient_key"], name="uniq_campaign_audience_recipient"),
        ]
        indexes = [
            models.Index(fields=["campaign", "status", "position"]),
        ]


class NotificationRecipientMessage(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "已创建"
        PROCESSING = "processing", "处理中"
        ACCEPTED = "accepted", "已受理"
        DELIVERED = "delivered", "已送达"
        PARTIAL = "partial", "部分完成"
        FAILED = "failed", "失败"
        SKIPPED = "skipped", "已跳过"

    campaign = models.ForeignKey(NotificationCampaign, null=True, blank=True, related_name="recipient_messages", on_delete=models.SET_NULL)
    intent = models.ForeignKey(NotificationIntent, null=True, blank=True, related_name="recipient_messages", on_delete=models.SET_NULL)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="notification_recipient_messages", on_delete=models.SET_NULL)
    recipient_type = models.CharField(max_length=16, default="user", db_index=True)
    recipient_key = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED, db_index=True)
    routing = models.JSONField(default=dict, blank=True)
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["campaign", "recipient_type", "recipient_key"], name="uniq_campaign_recipient_message"),
        ]


class NotificationMessage(models.Model):
    class Channel(models.TextChoices):
        APNS = "apns", "APNs"
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        IN_APP = "in_app", "站内信"

    class Status(models.TextChoices):
        QUEUED = "queued", "已入队"
        PROCESSING = "processing", "处理中"
        ACCEPTED = "accepted", "已受理"
        DELIVERED = "delivered", "已送达"
        SENT = "sent", "已发送"
        FAILED = "failed", "发送失败"
        PARTIAL = "partial", "部分成功"
        SKIPPED = "skipped", "已跳过"

    class RecipientType(models.TextChoices):
        USER = "user", "用户"
        CONTACT = "contact", "联系人"
        UNKNOWN = "unknown", "未知"

    campaign = models.ForeignKey(NotificationCampaign, null=True, blank=True, related_name="message_logs", on_delete=models.SET_NULL)
    intent = models.ForeignKey(NotificationIntent, null=True, blank=True, related_name="messages", on_delete=models.SET_NULL)
    recipient_message = models.ForeignKey(NotificationRecipientMessage, null=True, blank=True, related_name="channel_messages", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="notification_center_messages",
        on_delete=models.SET_NULL,
    )
    recipient_type = models.CharField(max_length=16, choices=RecipientType.choices, default=RecipientType.USER, db_index=True)
    recipient_key = models.CharField(max_length=255, blank=True, default="", db_index=True)
    channel = models.CharField(max_length=16, choices=Channel.choices, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SENT, db_index=True)
    title = models.CharField(max_length=255, blank=True, default="")
    body = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    delivery_details = models.JSONField(default=list, blank=True)
    target_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    receiver_email = models.EmailField(blank=True, default="")
    receiver_phone = models.CharField(max_length=32, blank=True, default="")
    apns_topic = models.CharField(max_length=255, blank=True, default="")
    provider_message_id = models.CharField(max_length=255, blank=True, default="")
    provider_request_id = models.CharField(max_length=255, blank=True, default="")
    provider_code = models.CharField(max_length=128, blank=True, default="")
    provider_status = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="notification_messages_created",
        on_delete=models.SET_NULL,
    )
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    delivered_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["channel", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]


class ContactEndpoint(models.Model):
    class Channel(models.TextChoices):
        APNS = "apns", "APNs"
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="contact_endpoints", on_delete=models.SET_NULL)
    channel = models.CharField(max_length=16, choices=Channel.choices, db_index=True)
    address_ciphertext = models.TextField(blank=True, default="")
    address_hmac = models.CharField(max_length=128, db_index=True)
    address_masked = models.CharField(max_length=255, blank=True, default="")
    is_verified = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    request_id = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["channel", "address_hmac"], name="uniq_contact_endpoint_channel_hmac"),
        ]


class ChannelDelivery(models.Model):
    class Channel(models.TextChoices):
        APNS = "apns", "APNs"
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    class Status(models.TextChoices):
        CREATED = "created", "已创建"
        QUEUED = "queued", "已入队"
        PROCESSING = "processing", "处理中"
        SUBMITTED = "submitted", "已提交"
        ACCEPTED = "accepted", "已受理"
        DELIVERED = "delivered", "已送达"
        DELIVERY_FAILED = "delivery_failed", "送达失败"
        SUBMIT_FAILED = "submit_failed", "提交失败"
        SUBMIT_UNKNOWN = "submit_unknown", "提交结果未知"
        CANCELLED = "cancelled", "已取消"
        EXPIRED = "expired", "已过期"

    message = models.ForeignKey(NotificationMessage, related_name="channel_deliveries", on_delete=models.CASCADE)
    channel = models.CharField(max_length=16, choices=Channel.choices, db_index=True)
    provider = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.CREATED, db_index=True)
    route_order = models.PositiveIntegerField(default=1)
    required = models.BooleanField(default=True)
    success_threshold = models.CharField(max_length=32, default="provider_accepted")
    endpoint_type = models.CharField(max_length=32, blank=True, default="")
    endpoint_hmac = models.CharField(max_length=128, blank=True, default="", db_index=True)
    endpoint_masked = models.CharField(max_length=255, blank=True, default="")
    provider_message_id = models.CharField(max_length=255, blank=True, default="")
    provider_request_id = models.CharField(max_length=255, blank=True, default="")
    provider_code = models.CharField(max_length=128, blank=True, default="")
    provider_status = models.CharField(max_length=64, blank=True, default="")
    accepted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=128, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    details = models.JSONField(default=dict, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["channel", "status", "-created_at"]),
            models.Index(fields=["endpoint_hmac"]),
        ]


class DeliveryAttempt(models.Model):
    class Outcome(models.TextChoices):
        SUCCESS = "success", "成功"
        FAILURE = "failure", "失败"
        UNKNOWN = "unknown", "未知"

    delivery = models.ForeignKey(ChannelDelivery, related_name="attempts", on_delete=models.CASCADE)
    attempt_no = models.PositiveIntegerField(default=1)
    provider_request_id = models.CharField(max_length=255, blank=True, default="")
    provider_message_id = models.CharField(max_length=255, blank=True, default="")
    request_payload = models.JSONField(default=dict, blank=True)
    response_code = models.CharField(max_length=128, blank=True, default="")
    response_message = models.TextField(blank=True, default="")
    outcome = models.CharField(max_length=16, choices=Outcome.choices, default=Outcome.UNKNOWN, db_index=True)
    error_category = models.CharField(max_length=128, blank=True, default="")
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["delivery", "attempt_no"], name="uniq_delivery_attempt_no"),
        ]
        indexes = [
            models.Index(fields=["delivery", "-attempt_no"]),
        ]


class ProviderEvent(models.Model):
    class NormalizedType(models.TextChoices):
        DELIVERED = "delivered", "已送达"
        DELIVERY_FAILED = "delivery_failed", "送达失败"
        SUBMITTED = "submitted", "已提交"
        UNKNOWN = "unknown", "未知"

    delivery = models.ForeignKey(ChannelDelivery, null=True, blank=True, related_name="provider_events", on_delete=models.SET_NULL)
    attempt = models.ForeignKey(DeliveryAttempt, null=True, blank=True, related_name="provider_events", on_delete=models.SET_NULL)
    provider = models.CharField(max_length=64, blank=True, default="")
    external_event_id = models.CharField(max_length=255, unique=True, db_index=True)
    normalized_type = models.CharField(max_length=32, choices=NormalizedType.choices, default=NormalizedType.UNKNOWN, db_index=True)
    provider_code = models.CharField(max_length=128, blank=True, default="")
    provider_status = models.CharField(max_length=128, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


class NotificationPreference(models.Model):
    class Channel(models.TextChoices):
        APNS = "apns", "APNs"
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="notification_preferences", on_delete=models.CASCADE)
    topic_key = models.CharField(max_length=128, db_index=True)
    channel = models.CharField(max_length=16, choices=Channel.choices, db_index=True)
    enabled = models.BooleanField(default=True, db_index=True)
    quiet_hours = models.JSONField(default=dict, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="notification_preferences_updated",
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "topic_key", "channel"], name="uniq_notification_preference"),
        ]


class NotificationSuppression(models.Model):
    class Channel(models.TextChoices):
        APNS = "apns", "APNs"
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        ALL = "all", "全部"

    class Reason(models.TextChoices):
        USER_OPT_OUT = "user_opt_out", "用户退订"
        HARD_BOUNCE = "hard_bounce", "硬退信"
        COMPLAINT = "complaint", "投诉"
        INVALID_ENDPOINT = "invalid_endpoint", "无效地址"
        POLICY = "policy", "策略抑制"

    endpoint_hmac = models.CharField(max_length=128, blank=True, default="", db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="notification_suppressions", on_delete=models.SET_NULL)
    channel = models.CharField(max_length=16, choices=Channel.choices, default=Channel.ALL, db_index=True)
    reason = models.CharField(max_length=32, choices=Reason.choices, db_index=True)
    detail = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="notification_suppressions_created",
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)


class NotificationOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "待处理"
        PROCESSING = "processing", "处理中"
        PROCESSED = "processed", "已处理"
        FAILED = "failed", "失败"

    aggregate_type = models.CharField(max_length=64, db_index=True)
    aggregate_id = models.CharField(max_length=128, db_index=True)
    event_type = models.CharField(max_length=128, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    available_at = models.DateTimeField(null=True, blank=True, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)


class NotificationAuditLog(models.Model):
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="notification_audits", on_delete=models.SET_NULL)
    action = models.CharField(max_length=128, db_index=True)
    target_type = models.CharField(max_length=64, db_index=True)
    target_id = models.CharField(max_length=128, db_index=True)
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
