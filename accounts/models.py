from django.contrib.auth.models import User
from django.db import models


class AccountProfile(models.Model):
    """
    Business fields that don't belong to Django's default User.
    Explicit OneToOne to auth.User (same pattern as ZhaodkDream UserProfile).
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone_number = models.CharField(max_length=32, blank=True, default="", db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"profile:{self.user_id}"


class TrustedDevice(models.Model):
    """
    可信设备（安装实例维度）。

    - 业务键：同一应用安装以 (bundle_id, device_id) 唯一；device_id 由客户端 Keychain 级 UUID 等稳定标识提供。
    - user 可空：允许匿名 POST /device/register/ 先落库，密码 / Apple / OTP 登录成功后再关联同一行。
    - 其余字段为终端画像与推送能力，供风控、运营触达与排障；verified / is_revoked 供后续设备证明或吊销策略扩展。
    """

    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        related_name="trusted_devices",
        on_delete=models.SET_NULL,
        db_comment="关联 Django User；匿名登记为空，登录成功后回填",
    )
    bundle_id = models.CharField(
        max_length=255,
        db_index=True,
        default="",
        db_comment="应用维度分组键，与 device_id 组成唯一约束（可与 bundle_identifier 相同或业务自定义）",
    )
    device_id = models.CharField(
        max_length=255,
        db_index=True,
        db_comment="客户端安装级稳定设备标识（如 Keychain UUID），与 bundle_id 唯一",
    )
    push_token = models.CharField(
        max_length=512,
        blank=True,
        default="",
        db_comment="APNs/FCM 等设备推送令牌（十六进制或供应商格式），可空",
    )
    notifications_enabled = models.BooleanField(
        default=False,
        db_comment="用户是否在系统设置中允许本应用通知（客户端上报）",
    )
    app_version = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_comment="面向用户的应用版本号（如 Marketing 版本）",
    )
    build_version = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_comment="构建号（CFBundleVersion 等）",
    )
    bundle_identifier = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_comment="包标识符（如 com.example.app），与 bundle_id 区分时可并存",
    )
    platform = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_comment="平台标识（如 ios、android）",
    )
    system_version = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_comment="操作系统版本字符串",
    )
    device_model = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_comment="设备硬件型号代码（如 iPhone15,2）",
    )
    device_model_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_comment="设备市场友好名称（若客户端可解析）",
    )
    device_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_comment="用户在系统中设置的设备名称（可能含隐私，注意展示策略）",
    )
    screen_size = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_comment="逻辑分辨率描述（如 393x852）",
    )
    screen_scale = models.FloatField(
        null=True,
        blank=True,
        db_comment="屏幕 scale（@2x/@3x 等）",
    )
    time_zone = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_comment="当前系统时区标识符",
    )
    language_code = models.CharField(
        max_length=10,
        blank=True,
        default="",
        db_comment="首选语言代码（BCP 47 或短码）",
    )
    region_code = models.CharField(
        max_length=10,
        blank=True,
        default="",
        db_comment="区域代码（如 CN、US）",
    )
    is_simulator = models.BooleanField(
        default=False,
        db_comment="是否在模拟器环境运行",
    )
    verified = models.BooleanField(
        default=False,
        db_comment="是否通过额外设备证明（预留，默认未验证）",
    )
    first_seen = models.DateTimeField(
        auto_now_add=True,
        db_comment="首次登记时间",
    )
    last_seen = models.DateTimeField(
        auto_now=True,
        db_comment="最近一次上报或刷新时间",
    )
    request_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_comment="关联网关或链路 request id，便于日志串联",
    )
    is_revoked = models.BooleanField(
        default=False,
        db_index=True,
        db_comment="是否已吊销（禁止推送或拒绝敏感操作等策略可读取）",
    )

    class Meta:
        db_table_comment = "客户端上报的可信安装实例：bundle_id+device_id 唯一，支持匿名后关联用户。"
        verbose_name = "可信设备"
        verbose_name_plural = "可信设备"
        constraints = [
            models.UniqueConstraint(fields=["bundle_id", "device_id"], name="uniq_bundle_device"),
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
        FROZEN = "frozen"
        ANONYMIZED = "anonymized"
        CLEANED_UP = "cleaned_up"
        DEACTIVATED = "deactivated"
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

    error_message = models.TextField(blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class AccountDeactivationAudit(models.Model):
    class AuditAction(models.TextChoices):
        FREEZE_IDENTIFIERS = "freeze_identifiers"
        ANONYMIZE = "anonymize"
        CLEANUP_OTPS = "cleanup_otps"
        DEACTIVATE_USER = "deactivate_user"
        CANCELLED = "cancelled"
        FAILED = "failed"

    deactivation = models.ForeignKey(AccountDeactivation, related_name="audits", on_delete=models.CASCADE)
    action = models.CharField(max_length=64, choices=AuditAction.choices, db_index=True)
    request_id = models.CharField(max_length=64, blank=True, default="")
    details = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
