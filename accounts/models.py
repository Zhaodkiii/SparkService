from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q


class AccountProfile(models.Model):
    """
    Business fields that don't belong to Django's default User.
    Login identifiers such as phone numbers live in SocialIdentity.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"profile:{self.user_id}"


class TrustedDevice(models.Model):
    """
    可信设备（安装实例 + 用户维度）。

    - 匿名：`(bundle_id, device_id, user=NULL)` 唯一，仅用于从未登录的安装（ACCOUNTS-000003）。
    - 已绑定用户：`(bundle_id, device_id, user)` 唯一；登录可将匿名行升级为当前用户行。
    - 退出后保留用户行并 `is_revoked=true`；未登录登记更新 revoked 行或匿名行，不凭 body 创建任意用户行。
    """

    user = models.ForeignKey(User, null=True, blank=True, related_name="trusted_devices", on_delete=models.SET_NULL, db_comment="关联 Django User；NULL=匿名冷启动画像，非 NULL=该用户设备行（与匿名行并存，不改绑匿名行）")
    bundle_id = models.CharField(max_length=255, db_index=True, default="", db_comment="应用维度分组键，与 device_id 组成唯一约束（可与 bundle_identifier 相同或业务自定义）")
    device_id = models.CharField(max_length=255, db_index=True, db_comment="客户端安装级稳定设备标识（如 Keychain UUID），与 bundle_id 唯一")
    push_token = models.CharField(max_length=512, blank=True, default="", db_comment="APNs/FCM 等设备推送令牌（十六进制或供应商格式），可空")
    notifications_enabled = models.BooleanField(default=False, db_comment="用户是否在系统设置中允许本应用通知（客户端上报）")
    app_version = models.CharField(max_length=50, blank=True, default="", db_comment="面向用户的应用版本号（如 Marketing 版本）")
    build_version = models.CharField(max_length=50, blank=True, default="", db_comment="构建号（CFBundleVersion 等）")
    bundle_identifier = models.CharField(max_length=255, blank=True, default="", db_comment="包标识符（如 com.example.app），与 bundle_id 区分时可并存")
    platform = models.CharField(max_length=20, blank=True, default="", db_comment="平台标识（如 ios、android）")
    system_version = models.CharField(max_length=50, blank=True, default="", db_comment="操作系统版本字符串")
    device_model = models.CharField(max_length=100, blank=True, default="", db_comment="设备硬件型号代码（如 iPhone15,2）")
    device_model_name = models.CharField(max_length=100, blank=True, default="", db_comment="设备市场友好名称（若客户端可解析）")
    device_name = models.CharField(max_length=255, blank=True, default="", db_comment="用户在系统中设置的设备名称（可能含隐私，注意展示策略）")
    screen_size = models.CharField(max_length=50, blank=True, default="", db_comment="逻辑分辨率描述（如 393x852）")
    screen_scale = models.FloatField(null=True, blank=True, db_comment="屏幕 scale（@2x/@3x 等）")
    time_zone = models.CharField(max_length=50, blank=True, default="", db_comment="当前系统时区标识符")
    language_code = models.CharField(max_length=10, blank=True, default="", db_comment="首选语言代码（BCP 47 或短码）")
    region_code = models.CharField(max_length=10, blank=True, default="", db_comment="区域代码（如 CN、US）")
    country_code = models.CharField(max_length=10, blank=True, default="", db_index=True, db_comment="客户端 SparkSystemInfo.mostLikelyCountryCode 推断的最可能国家/地区标识，可空")
    is_simulator = models.BooleanField(default=False, db_comment="是否在模拟器环境运行")
    verified = models.BooleanField(default=False, db_comment="是否通过额外设备证明（预留，默认未验证）")
    first_seen = models.DateTimeField(auto_now_add=True, db_comment="首次登记时间")
    last_seen = models.DateTimeField(auto_now=True, db_comment="最近一次上报或刷新时间")
    request_id = models.CharField(max_length=64, blank=True, default="", db_comment="关联网关或链路 request id，便于日志串联")
    is_revoked = models.BooleanField(default=False, db_index=True, db_comment="是否已吊销（禁止推送或拒绝敏感操作等策略可读取）")

    class Meta:
        db_table_comment = "客户端上报的可信安装实例：匿名 bundle+device 唯一；已登录用户 bundle+device+user 唯一。"
        verbose_name = "可信设备"
        verbose_name_plural = "可信设备"
        constraints = [
            models.UniqueConstraint(
                fields=["bundle_id", "device_id"],
                condition=Q(user__isnull=True),
                name="uniq_bundle_device_anonymous",
            ),
            models.UniqueConstraint(
                fields=["bundle_id", "device_id", "user"],
                condition=Q(user__isnull=False),
                name="uniq_bundle_device_user_bound",
            ),
        ]


class AccountDeviceSession(models.Model):
    """
    用户当前有效登录设备会话（与 TrustedDevice 安装画像解耦）。

  同一用户同一时间最多一个 ACTIVE 会话；新设备登录会将旧会话标记为 REVOKED。
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "有效"
        REVOKED = "revoked", "已失效"
        LOGGED_OUT = "logged_out", "已退出"

    user = models.ForeignKey(User, related_name="device_sessions", on_delete=models.CASCADE, db_comment="所属用户")
    trusted_device = models.ForeignKey(
        TrustedDevice,
        related_name="account_sessions",
        on_delete=models.CASCADE,
        db_comment="绑定的可信设备安装实例",
    )
    bundle_id = models.CharField(max_length=255, db_index=True, default="", db_comment="登录时 bundle_id 快照")
    device_id = models.CharField(max_length=255, db_index=True, default="", db_comment="登录时 device_id 快照")
    session_version = models.PositiveIntegerField(default=1, db_index=True, db_comment="会话版本号，写入 JWT claim")
    refresh_jti = models.CharField(max_length=255, blank=True, default="", db_index=True, db_comment="当前 refresh token jti")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        db_comment="会话状态",
    )
    revoked_reason = models.CharField(max_length=64, blank=True, default="", db_comment="失效原因（如 replaced_by_new_device）")
    replaced_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replaced_sessions",
        db_comment="被哪条新会话替换",
    )
    last_refreshed_at = models.DateTimeField(null=True, blank=True, db_comment="最近一次 refresh 成功时间")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table_comment = "账号设备登录会话：单用户单 ACTIVE，供 token 校验与 APNs 投递。"
        verbose_name = "设备登录会话"
        verbose_name_plural = "设备登录会话"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="active"),
                name="uniq_active_device_session_per_user",
            ),
        ]


class LoginAudit(models.Model):
    class LoginProvider(models.TextChoices):
        PASSWORD = "password"
        EMAIL_OTP = "email_otp"
        PHONE_OTP = "phone_otp"
        GOOGLE = "google"
        APPLE = "apple"

    class LoginOutcome(models.TextChoices):
        SUCCESS = "success"
        FAILED = "failed"

    user = models.ForeignKey(User, null=True, blank=True, related_name="login_audits", on_delete=models.SET_NULL)
    provider = models.CharField(max_length=32, choices=LoginProvider.choices)
    outcome = models.CharField(max_length=16, choices=LoginOutcome.choices, db_index=True)
    ip_address = models.CharField(max_length=64, blank=True, default="")
    user_agent = models.TextField(blank=True, default="")
    bundle_id = models.CharField(max_length=128, blank=True, default="")
    device_id = models.CharField(max_length=128, blank=True, default="")
    raw_claims = models.JSONField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class SocialIdentity(models.Model):
    class Provider(models.TextChoices):
        APPLE = "apple"
        GOOGLE = "google"
        PHONE = "phone"

    user = models.ForeignKey(User, related_name="social_identities", on_delete=models.CASCADE)
    provider = models.CharField(max_length=32, choices=Provider.choices, db_index=True)
    provider_uid = models.CharField(max_length=255, db_index=True)
    bundle_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bundle_id", "provider", "provider_uid"],
                name="uniq_social_identity_bundle_provider_uid",
            ),
        ]


class EmailOTP(models.Model):
    otp_id = models.CharField(max_length=64, unique=True, db_index=True)
    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=64, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    # Dimensions for rate limiting / anomaly detection.
    provider_uid = models.CharField(max_length=128, blank=True, default="", db_index=True)
    bundle_id = models.CharField(max_length=128, blank=True, default="")
    device_id = models.CharField(max_length=128, blank=True, default="")
    ip_address = models.CharField(max_length=64, blank=True, default="")

    request_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["email", "expires_at"]),
        ]


class PhoneOTP(models.Model):
    otp_id = models.CharField(max_length=64, unique=True, db_index=True)
    phone_number = models.CharField(max_length=32, db_index=True)
    code_hash = models.CharField(max_length=64, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    provider_uid = models.CharField(max_length=128, blank=True, default="", db_index=True)
    bundle_id = models.CharField(max_length=128, blank=True, default="")
    device_id = models.CharField(max_length=128, blank=True, default="")
    ip_address = models.CharField(max_length=64, blank=True, default="")

    request_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["phone_number", "expires_at"]),
        ]


class AccountDeactivation(models.Model):
    class DeactivationState(models.TextChoices):
        REQUESTED = "requested"
        SCHEDULED = "scheduled"
        DATA_BACKED_UP = "data_backed_up"
        ANONYMIZED = "anonymized"
        RELATED_DATA_DELETED = "related_data_deleted"
        ACCOUNT_DISABLED = "account_disabled"
        COMPLETED = "completed"
        CANCELLED = "cancelled"
        FAILED = "failed"

    user = models.ForeignKey(User, related_name="deactivations", on_delete=models.CASCADE)
    state = models.CharField(max_length=32, choices=DeactivationState.choices, db_index=True, default=DeactivationState.REQUESTED)

    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    # Freeze original identifiers for compliance-safe deletion order.
    freeze_email = models.EmailField(blank=True, default="")
    freeze_phone_number = models.CharField(max_length=32, blank=True, default="")

    reason = models.CharField(max_length=256, blank=True, default="")
    data_retention_days = models.PositiveIntegerField(default=30)
    anonymize_personal_data = models.BooleanField(default=True)
    delete_related_data = models.BooleanField(default=True)
    backup_uri = models.CharField(max_length=1024, blank=True, default="")
    backup_checksum = models.CharField(max_length=128, blank=True, default="")
    backup_expires_at = models.DateTimeField(null=True, blank=True)

    error_message = models.TextField(blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class AccountDeactivationAudit(models.Model):
    class AuditAction(models.TextChoices):
        REQUESTED = "requested"
        DATA_BACKUP = "data_backup"
        DATA_ANONYMIZE = "data_anonymize"
        RELATED_DATA_DELETE = "related_data_delete"
        ACCOUNT_DEACTIVATE = "account_deactivate"
        COMPLETED = "completed"
        CANCELLED = "cancelled"
        FAILED = "failed"

    deactivation = models.ForeignKey(AccountDeactivation, related_name="audits", on_delete=models.CASCADE)
    action = models.CharField(max_length=64, choices=AuditAction.choices, db_index=True)
    request_id = models.CharField(max_length=64, blank=True, default="")
    details = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class NotificationTemplate(models.Model):
    name = models.CharField(max_length=128, unique=True, db_index=True)
    description = models.CharField(max_length=255, blank=True, default="")
    title_template = models.CharField(max_length=255, blank=True, default="")
    body_template = models.TextField(blank=True, default="")
    payload_template = models.JSONField(default=dict, blank=True)
    default_channels = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "-updated_at"]),
        ]

    def __str__(self):
        return f"notification_template:{self.id}:{self.name}"


class NotificationCampaign(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "待发送"
        SCHEDULED = "scheduled", "定时中"
        RUNNING = "running", "发送中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失败"

    name = models.CharField(max_length=128, blank=True, default="")
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
    template = models.ForeignKey("NotificationTemplate", null=True, blank=True, related_name="campaigns", on_delete=models.SET_NULL)
    created_by = models.ForeignKey(User, null=True, blank=True, related_name="notification_campaigns", on_delete=models.SET_NULL)
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
            models.Index(fields=["-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"notification_campaign:{self.id}:{self.status}"


class NotificationMessage(models.Model):
    """
    后台通知发送记录（按渠道一条记录）。

    - 一次后台“发送”操作可拆分为多条记录（APNs / Email / SMS）。
    - APNs 记录中可通过 delivery_details 保存逐设备结果。
    """

    class Channel(models.TextChoices):
        APNS = "apns", "APNs"
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    class Status(models.TextChoices):
        SENT = "sent", "已发送"
        FAILED = "failed", "发送失败"
        PARTIAL = "partial", "部分成功"
        SKIPPED = "skipped", "已跳过"

    user = models.ForeignKey(
        User,
        related_name="notification_messages",
        on_delete=models.CASCADE,
    )
    campaign = models.ForeignKey(
        "NotificationCampaign",
        null=True,
        blank=True,
        related_name="message_logs",
        on_delete=models.SET_NULL,
    )
    channel = models.CharField(max_length=16, choices=Channel.choices, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, db_index=True, default=Status.SENT)

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
    error_message = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        related_name="sent_notification_messages",
        on_delete=models.SET_NULL,
    )
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["channel", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"notification:{self.id}:{self.channel}:{self.status}:user={self.user_id}"
