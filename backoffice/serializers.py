from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from accounts.models import (
    AccessDenyEntry,
    AccessDenyHit,
    AccountDeactivation,
    AccountDeactivationAudit,
    AccountDeviceSession,
    LoginAudit,
    SocialIdentity,
    TrustedDevice,
)
from backoffice.masking import mask_email, mask_phone
from backoffice.models import AdminAuditLog, AdminPermission, AdminRole
from notification_center.models import NotificationCampaign, NotificationMessage, NotificationTemplate


User = get_user_model()


def _normalize_ai_tool_scenarios(value):
    """`ai_tool_scenarios` JSON 字段：仅允许字符串数组。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if x is not None and str(x).strip() != ""]
    raise serializers.ValidationError("ai_tool_scenarios_must_be_string_array")


def _normalize_string_list(value, field_name: str):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if x is not None and str(x).strip() != ""]
    raise serializers.ValidationError(f"{field_name}_must_be_string_array")


class AdminUserSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "display_name",
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
        )

    def get_display_name(self, obj):
        name = (getattr(obj, "first_name", None) or "").strip()
        if name:
            return name
        return obj.username


def _compute_last_used_at(user):
    candidates = []
    max_device_seen = getattr(user, "_max_device_seen", None)
    max_session_refresh = getattr(user, "_max_session_refresh", None)
    if max_device_seen is not None:
        candidates.append(max_device_seen)
    if max_session_refresh is not None:
        candidates.append(max_session_refresh)
    if user.last_login is not None:
        candidates.append(user.last_login)
    if not candidates:
        return None
    return max(candidates)


class AdminUserListSerializer(AdminUserSerializer):
    last_used_at = serializers.SerializerMethodField()
    is_pro = serializers.SerializerMethodField()
    pro_status = serializers.SerializerMethodField()
    pro_expires_at = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()

    class Meta(AdminUserSerializer.Meta):
        fields = AdminUserSerializer.Meta.fields + (
            "last_used_at",
            "is_pro",
            "pro_status",
            "pro_expires_at",
            "phone_number",
        )

    def get_phone_number(self, obj):
        identities = getattr(obj, "_phone_identities", None)
        if identities:
            return (identities[0].provider_uid or "").strip()
        identity = (
            SocialIdentity.objects.filter(user=obj, provider=SocialIdentity.Provider.PHONE)
            .order_by("-updated_at", "-id")
            .first()
        )
        return (identity.provider_uid if identity else "") or ""

    def get_last_used_at(self, obj):
        return _compute_last_used_at(obj)

    def get_is_pro(self, obj):
        return False

    def get_pro_status(self, obj):
        return "none"

    def get_pro_expires_at(self, obj):
        return None


class AdminUserStatusSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()


class AdminAccessDenyCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False, allow_null=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    device_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    reason_note = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs):
        user_id = attrs.get("user_id")
        phone = (attrs.get("phone") or "").strip()
        email = (attrs.get("email") or "").strip().lower()
        device_id = (attrs.get("device_id") or "").strip()
        provided = sum(bool(x) for x in [user_id, phone, email, device_id])
        if provided != 1:
            raise serializers.ValidationError("user_id、phone、email、device_id 必须且只能提供一个")
        attrs["phone"] = phone
        attrs["email"] = email
        attrs["device_id"] = device_id
        return attrs


class AdminAccessDenyEntrySerializer(serializers.ModelSerializer):
    is_active = serializers.SerializerMethodField()
    display_value = serializers.SerializerMethodField()
    sms_status = serializers.SerializerMethodField()
    related_user_display = serializers.SerializerMethodField()

    class Meta:
        model = AccessDenyEntry
        fields = (
            "id",
            "dimension",
            "dimension_value",
            "display_value",
            "reason_code",
            "reason_note",
            "source",
            "related_user_id",
            "related_user_display",
            "expires_at",
            "revoked_at",
            "is_active",
            "sms_status",
            "created_by_id",
            "metadata",
            "created_at",
            "updated_at",
        )

    def get_is_active(self, obj):
        if obj.revoked_at is not None:
            return False
        if obj.expires_at and obj.expires_at <= timezone.now():
            return False
        return True

    def get_display_value(self, obj):
        return obj.dimension_value

    def get_sms_status(self, obj):
        metadata = obj.metadata if isinstance(obj.metadata, dict) else {}
        return metadata.get("sms_status", "")

    def get_related_user_display(self, obj):
        if not obj.related_user_id:
            return ""
        user = User.objects.filter(id=obj.related_user_id).only("username", "first_name", "email").first()
        if user is None:
            return str(obj.related_user_id)
        name = (getattr(user, "first_name", None) or "").strip()
        return name or user.username or str(user.id)


class AdminAccessDenyHitSerializer(serializers.ModelSerializer):
    attempted_identity = serializers.SerializerMethodField()

    class Meta:
        model = AccessDenyHit
        fields = (
            "id",
            "deny_entry_id",
            "action",
            "hit_dimension",
            "hit_value",
            "reason_code",
            "provider",
            "attempted_user_id",
            "attempted_email",
            "attempted_phone",
            "attempted_identity",
            "device_id",
            "bundle_id",
            "ip_address",
            "user_agent",
            "request_id",
            "created_at",
        )

    def get_attempted_identity(self, obj):
        if obj.attempted_user_id:
            return f"user:{obj.attempted_user_id}"
        if obj.attempted_email:
            return obj.attempted_email
        if obj.attempted_phone:
            return obj.attempted_phone
        return ""


_SOCIAL_PROVIDER_LABELS = {
    SocialIdentity.Provider.APPLE: "Apple",
    SocialIdentity.Provider.GOOGLE: "Google",
    SocialIdentity.Provider.PHONE: "手机",
    SocialIdentity.Provider.EMAIL: "邮箱",
    SocialIdentity.Provider.DEVICE: "设备",
}


def mask_provider_uid(*, provider: str, provider_uid: str) -> str:
    uid = (provider_uid or "").strip()
    if not uid:
        return ""
    if provider == SocialIdentity.Provider.EMAIL:
        return mask_email(uid, reveal=False)
    if provider == SocialIdentity.Provider.PHONE:
        return mask_phone(uid, reveal=False)
    if len(uid) <= 14:
        return f"{uid[:6]}..." if len(uid) > 6 else "***"
    return f"{uid[:10]}...{uid[-4:]}"


class AdminUserSocialIdentitySerializer(serializers.ModelSerializer):
    provider_label = serializers.SerializerMethodField()
    provider_uid_masked = serializers.SerializerMethodField()

    class Meta:
        model = SocialIdentity
        fields = (
            "id",
            "provider",
            "provider_label",
            "provider_uid_masked",
            "bundle_id",
            "created_at",
            "updated_at",
        )

    def get_provider_label(self, obj: SocialIdentity) -> str:
        return _SOCIAL_PROVIDER_LABELS.get(obj.provider, obj.provider or "-")

    def get_provider_uid_masked(self, obj: SocialIdentity) -> str:
        return mask_provider_uid(provider=obj.provider, provider_uid=obj.provider_uid) or "-"


def mask_push_token(token: str) -> str:
    t = (token or "").strip()
    if not t:
        return ""
    if len(t) <= 12:
        return "***"
    return f"{t[:6]}...{t[-6:]}"


class AdminUserTrustedDeviceSerializer(serializers.ModelSerializer):
    push_token_masked = serializers.SerializerMethodField()

    class Meta:
        model = TrustedDevice
        fields = (
            "id",
            "bundle_id",
            "device_id",
            "app_version",
            "build_version",
            "bundle_identifier",
            "push_token_masked",
            "notifications_enabled",
            "platform",
            "system_version",
            "device_model",
            "device_model_name",
            "device_name",
            "country_code",
            "region_code",
            "language_code",
            "is_simulator",
            "is_revoked",
            "first_seen",
            "last_seen",
            "request_id",
        )

    def get_push_token_masked(self, obj: TrustedDevice) -> str:
        return mask_push_token(obj.push_token)


class AdminUserDeviceSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountDeviceSession
        fields = (
            "id",
            "trusted_device",
            "bundle_id",
            "device_id",
            "session_version",
            "status",
            "revoked_reason",
            "replaced_by",
            "last_refreshed_at",
            "created_at",
            "updated_at",
        )


class AdminDeviceSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = TrustedDevice
        fields = (
            "id",
            "user",
            "user_name",
            "user_email",
            "bundle_id",
            "device_id",
            "platform",
            "system_version",
            "device_model",
            "device_name",
            "verified",
            "notifications_enabled",
            "is_revoked",
            "first_seen",
            "last_seen",
        )


class AdminDeviceRevokeSerializer(serializers.Serializer):
    is_revoked = serializers.BooleanField()


class AdminDeactivationSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = AccountDeactivation
        fields = (
            "id",
            "user",
            "user_name",
            "user_email",
            "state",
            "requested_at",
            "scheduled_at",
            "processed_at",
            "completed_at",
            "cancelled_at",
            "failed_at",
            "freeze_email",
            "freeze_phone_number",
            "error_message",
            "request_id",
            "created_at",
        )


class AdminDeactivationAuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountDeactivationAudit
        fields = (
            "id",
            "deactivation",
            "action",
            "request_id",
            "details",
            "created_at",
        )


class AdminNotificationSendSerializer(serializers.Serializer):
    campaign_name = serializers.CharField(required=False, allow_blank=True, max_length=128, default="")
    template_id = serializers.IntegerField(required=False, allow_null=True)
    user_id = serializers.IntegerField(required=False, allow_null=True)
    user_ids = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=True)
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    body = serializers.CharField(required=False, allow_blank=True)
    channels = serializers.ListField(
        child=serializers.ChoiceField(choices=[NotificationMessage.Channel.APNS, NotificationMessage.Channel.EMAIL, NotificationMessage.Channel.SMS]),
        allow_empty=False,
    )
    filters = serializers.JSONField(required=False)
    payload = serializers.JSONField(required=False)
    schedule_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        template_id = attrs.get("template_id")
        title = (attrs.get("title") or "").strip()
        body = (attrs.get("body") or "").strip()
        user_id = attrs.get("user_id")
        user_ids = attrs.get("user_ids") or []
        filters = attrs.get("filters") or {}
        if not template_id and not (title or body):
            raise serializers.ValidationError("template_id 或 title/body 至少提供一组")
        if not user_id and not user_ids and not filters:
            raise serializers.ValidationError("请指定 user_id / user_ids / filters 至少一种目标")
        return attrs


from notification_center.serializers import AdminNotificationUserListQuerySerializer as AdminNotificationUserQuerySerializer


class AdminNotificationLogQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, default="")
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=20)
    status = serializers.ChoiceField(
        required=False,
        allow_blank=True,
        choices=[
            "",
            NotificationMessage.Status.QUEUED,
            NotificationMessage.Status.PROCESSING,
            NotificationMessage.Status.ACCEPTED,
            NotificationMessage.Status.DELIVERED,
            NotificationMessage.Status.SENT,
            NotificationMessage.Status.FAILED,
            NotificationMessage.Status.PARTIAL,
            NotificationMessage.Status.SKIPPED,
        ],
        default="",
    )


class AdminNotificationMessageSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    recipient_key = serializers.SerializerMethodField()
    body = serializers.SerializerMethodField()
    payload = serializers.SerializerMethodField()

    def get_recipient_key(self, obj):
        if obj.channel == NotificationMessage.Channel.SMS:
            return obj.receiver_phone or "***"
        if obj.channel == NotificationMessage.Channel.EMAIL:
            return obj.receiver_email or "***"
        return "***"

    def get_body(self, obj):
        text = (obj.body or "").strip()
        if not text:
            return ""
        return text[:120] + ("..." if len(text) > 120 else "")

    def get_payload(self, obj):
        if not isinstance(obj.payload, dict):
            return {}
        return {"keys": sorted(obj.payload.keys())}

    class Meta:
        model = NotificationMessage
        fields = (
            "id",
            "campaign",
            "campaign_name",
            "user",
            "user_name",
            "recipient_type",
            "recipient_key",
            "channel",
            "status",
            "title",
            "body",
            "payload",
            "delivery_details",
            "target_count",
            "success_count",
            "failure_count",
            "receiver_email",
            "receiver_phone",
            "apns_topic",
            "provider_message_id",
            "error_message",
            "request_id",
            "sent_at",
            "created_at",
            "updated_at",
        )


class AdminNotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = (
            "id",
            "name",
            "description",
            "title_template",
            "body_template",
            "payload_template",
            "default_channels",
            "is_active",
            "created_at",
            "updated_at",
        )


class AdminNotificationCampaignSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)
    template_name = serializers.CharField(source="template.name", read_only=True)

    class Meta:
        model = NotificationCampaign
        fields = (
            "id",
            "name",
            "status",
            "channels",
            "title",
            "body",
            "payload",
            "filters",
            "target_user_ids",
            "target_count",
            "success_count",
            "failure_count",
            "template",
            "template_name",
            "created_by",
            "created_by_name",
            "task_id",
            "request_id",
            "scheduled_at",
            "started_at",
            "finished_at",
            "error_message",
            "created_at",
            "updated_at",
        )


class AdminNotificationTemplatePreviewSerializer(serializers.Serializer):
    template_id = serializers.IntegerField(required=False, allow_null=True)
    user_id = serializers.IntegerField(required=False, allow_null=True)
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    body = serializers.CharField(required=False, allow_blank=True)
    payload = serializers.JSONField(required=False)


class AdminRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminRole
        fields = ("id", "name", "code", "description", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class AdminPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminPermission
        fields = (
            "id",
            "name",
            "code",
            "permission_type",
            "path",
            "method",
            "parent_code",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class AdminRolePermissionAssignSerializer(serializers.Serializer):
    permission_codes = serializers.ListField(child=serializers.CharField(max_length=128), allow_empty=True)


class AdminUserRoleAssignSerializer(serializers.Serializer):
    role_codes = serializers.ListField(child=serializers.CharField(max_length=64), allow_empty=True)


class AdminAuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = AdminAuditLog
        fields = (
            "id",
            "user",
            "user_name",
            "action",
            "resource_type",
            "resource_id",
            "method",
            "path",
            "status_code",
            "request_id",
            "ip_address",
            "user_agent",
            "request_payload",
            "response_payload",
            "created_at",
        )


class AdminLoginAuditSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = LoginAudit
        fields = (
            "id",
            "user",
            "user_name",
            "provider",
            "outcome",
            "ip_address",
            "user_agent",
            "bundle_id",
            "device_id",
            "raw_claims",
            "request_id",
            "created_at",
        )

    def get_user_name(self, obj):
        if obj.user_id and obj.user:
            return obj.user.username
        return ""
