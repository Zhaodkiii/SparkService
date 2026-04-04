from django.conf import settings
from django.db import models
from django.utils import timezone


class AccountProfile(models.Model):
    """
    Business fields that don't belong to Django's default User.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="profile", on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=32, blank=True, default="", db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"profile:{self.user_id}"


class TrustedDevice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="trusted_devices", on_delete=models.CASCADE)
    device_id = models.CharField(max_length=128, db_index=True)
    bundle_id = models.CharField(max_length=128, blank=True, default="")
    nickname = models.CharField(max_length=64, blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default="")
    is_revoked = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "device_id"], name="uniq_trusted_device_per_user"),
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

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="login_audits", on_delete=models.SET_NULL)
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

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="social_identities", on_delete=models.CASCADE)
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

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="deactivations", on_delete=models.CASCADE)
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
