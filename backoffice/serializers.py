from django.contrib.auth import get_user_model
from rest_framework import serializers

from ai_config.models import (
    AIModelCatalog,
    AIProviderKeyConfig,
    AIScenarioModelBinding,
    IdentityKind,
    ScenarioKey,
    SmallTask,
    TrialApplication,
    TrialApplicationRequest,
)
from accounts.models import (
    AccountDeactivation,
    AccountDeactivationAudit,
    AccountDeviceSession,
    NotificationCampaign,
    NotificationMessage,
    NotificationTemplate,
    TrustedDevice,
)
from app_version.serializers import AppVersionConfigSerializer, VersionCheckLogSerializer
from backoffice.models import AdminAuditLog, AdminPermission, AdminRole


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
    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
        )


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

    class Meta(AdminUserSerializer.Meta):
        fields = AdminUserSerializer.Meta.fields + ("last_used_at",)

    def get_last_used_at(self, obj):
        return _compute_last_used_at(obj)


class AdminUserStatusSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()


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


class AdminNotificationUserQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, default="")
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=20)
    only_enabled = serializers.BooleanField(required=False, default=True)
    has_email = serializers.BooleanField(required=False, allow_null=True)
    has_sms = serializers.BooleanField(required=False, allow_null=True)
    has_apns = serializers.BooleanField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, allow_null=True)


class AdminNotificationLogQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, default="")
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=20)
    status = serializers.ChoiceField(
        required=False,
        allow_blank=True,
        choices=["", NotificationMessage.Status.SENT, NotificationMessage.Status.FAILED, NotificationMessage.Status.PARTIAL, NotificationMessage.Status.SKIPPED],
        default="",
    )


class AdminNotificationMessageSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)

    class Meta:
        model = NotificationMessage
        fields = (
            "id",
            "campaign",
            "campaign_name",
            "user",
            "user_name",
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


class AdminAIScenarioSummarySerializer(serializers.Serializer):
    """One row per fixed scenario key (list/overview)."""

    scenario = serializers.CharField()
    label = serializers.CharField()
    models_count = serializers.IntegerField()
    default_model = serializers.CharField(allow_null=True)
    active_bindings = serializers.IntegerField()


def _resolve_provider_for_catalog_model(model_obj: AIModelCatalog):
    return (
        AIProviderKeyConfig.objects.filter(
            kind=AIProviderKeyConfig.Kind.API,
            company=model_obj.company,
            is_active=True,
        )
        .order_by("-is_using", "position", "name")
        .first()
    )


class AdminAIScenarioModelBindingSerializer(serializers.ModelSerializer):
    model = serializers.SlugRelatedField(slug_field="name", queryset=AIModelCatalog.objects.filter(is_active=True))
    model_id = serializers.IntegerField(read_only=True)
    display_name = serializers.CharField(max_length=128, trim_whitespace=False)
    bootstrap_name = serializers.SerializerMethodField()
    endpoint = serializers.SerializerMethodField()
    provider_company = serializers.SerializerMethodField()
    provider_name = serializers.SerializerMethodField()

    class Meta:
        model = AIScenarioModelBinding
        fields = (
            "id",
            "scenario",
            "identity",
            "model",
            "model_id",
            "display_name",
            "bootstrap_name",
            "endpoint",
            "provider_company",
            "provider_name",
            "temperature",
            "max_tokens",
            "position",
            "is_default",
            "is_active",
            "system_provision",
            "brief_description",
            "ai_tool_scenarios",
            "related_task_codes",
            "updated_at",
            "created_at",
        )
        read_only_fields = ("id", "scenario", "updated_at", "created_at")

    def validate_ai_tool_scenarios(self, value):
        return _normalize_ai_tool_scenarios(value)

    def validate_related_task_codes(self, value):
        return _normalize_string_list(value, "related_task_codes")

    def validate_display_name(self, value):
        text = "" if value is None else str(value).strip()
        if not text:
            raise serializers.ValidationError("display_name_required")
        return text

    def _resolve_provider(self, obj: AIScenarioModelBinding):
        return _resolve_provider_for_catalog_model(obj.model)

    def get_bootstrap_name(self, obj):
        return obj.bootstrap_name()

    def get_endpoint(self, obj):
        p = self._resolve_provider(obj)
        return p.request_url if p else ""

    def get_provider_company(self, obj):
        p = self._resolve_provider(obj)
        return p.company if p else obj.model.company

    def get_provider_name(self, obj):
        p = self._resolve_provider(obj)
        return p.name if p else ""

    def validate(self, attrs):
        model_obj = attrs.get("model")
        if self.instance and model_obj is None:
            model_obj = self.instance.model
        if model_obj is None:
            return attrs
        if _resolve_provider_for_catalog_model(model_obj) is None:
            raise serializers.ValidationError({"model": "provider_not_configured_for_model_company"})
        scenario = self.context.get("scenario") or (self.instance.scenario if self.instance else None)
        identity = attrs.get("identity")
        if identity is None and self.instance is not None:
            identity = self.instance.identity
        elif identity is None:
            identity = IdentityKind.MODEL
        if scenario and identity == IdentityKind.MODEL:
            duplicate_qs = AIScenarioModelBinding.objects.filter(
                scenario=scenario,
                model=model_obj,
                identity=IdentityKind.MODEL,
            )
            if self.instance is not None:
                duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)
            if duplicate_qs.exists():
                raise serializers.ValidationError({"model": "model_already_bound_to_this_scenario_with_same_identity"})
        if scenario and self.instance is None and not AIScenarioModelBinding.objects.filter(scenario=scenario).exists():
            attrs.setdefault("is_default", True)
        return attrs

    def create(self, validated_data):
        scenario = self.context.get("scenario")
        if not scenario:
            raise serializers.ValidationError({"scenario": "missing_context"})
        validated_data["scenario"] = scenario
        inst = super().create(validated_data)
        if inst.is_default:
            self._clear_defaults(inst.scenario, exclude_pk=inst.pk)
        return inst

    def update(self, instance, validated_data):
        inst = super().update(instance, validated_data)
        if inst.is_default:
            self._clear_defaults(inst.scenario, exclude_pk=inst.pk)
        return inst

    @staticmethod
    def _clear_defaults(scenario: str, exclude_pk: int):
        AIScenarioModelBinding.objects.filter(scenario=scenario, is_default=True).exclude(pk=exclude_pk).update(
            is_default=False,
            default_marker=None,
        )


def _validate_price_tier(value) -> int:
    if value is None:
        return 0
    v = int(value)
    if v < 0 or v > 3:
        raise serializers.ValidationError("price_tier_must_be_0_3")
    return v


class AdminAIModelCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModelCatalog
        fields = (
            "id",
            "name",
            "display_name",
            "position",
            "company",
            "is_hidden",
            "supports_search",
            "supports_multimodal",
            "supports_reasoning",
            "supports_tool_use",
            "supports_voice_gen",
            "supports_image_gen",
            "price_tier",
            "supports_text",
            "reasoning_controllable",
            "icon",
            "related_task_codes",
            "source",
            "is_active",
            "updated_at",
            "created_at",
        )
        read_only_fields = ("id", "updated_at", "created_at")


class AdminAIModelCatalogCreateSerializer(serializers.ModelSerializer):
    def validate_company(self, value):
        company = (value or "").strip()
        if not company:
            raise serializers.ValidationError("company_required")
        exists = AIProviderKeyConfig.objects.filter(
            kind=AIProviderKeyConfig.Kind.API,
            company=company,
            is_active=True,
        ).exists()
        if not exists:
            raise serializers.ValidationError("company_provider_not_found_or_inactive")
        return company

    class Meta:
        model = AIModelCatalog
        fields = (
            "name",
            "display_name",
            "position",
            "company",
            "is_hidden",
            "supports_search",
            "supports_multimodal",
            "supports_reasoning",
            "supports_tool_use",
            "supports_voice_gen",
            "supports_image_gen",
            "price_tier",
            "supports_text",
            "reasoning_controllable",
            "icon",
            "related_task_codes",
            "source",
            "is_active",
        )

    def validate_price_tier(self, value):
        return _validate_price_tier(value)

    def validate_related_task_codes(self, value):
        return _normalize_string_list(value, "related_task_codes")


class AdminAIModelCatalogUpdateSerializer(serializers.ModelSerializer):
    def validate_company(self, value):
        company = (value or "").strip()
        if not company:
            raise serializers.ValidationError("company_required")
        exists = AIProviderKeyConfig.objects.filter(
            kind=AIProviderKeyConfig.Kind.API,
            company=company,
            is_active=True,
        ).exists()
        if not exists:
            raise serializers.ValidationError("company_provider_not_found_or_inactive")
        return company

    class Meta:
        model = AIModelCatalog
        fields = (
            "display_name",
            "position",
            "company",
            "is_hidden",
            "supports_search",
            "supports_multimodal",
            "supports_reasoning",
            "supports_tool_use",
            "supports_voice_gen",
            "supports_image_gen",
            "price_tier",
            "supports_text",
            "reasoning_controllable",
            "icon",
            "related_task_codes",
            "source",
            "is_active",
        )

    def validate_price_tier(self, value):
        return _validate_price_tier(value)

    def validate_related_task_codes(self, value):
        return _normalize_string_list(value, "related_task_codes")


class AdminSmallTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmallTask
        fields = (
            "id",
            "name",
            "code",
            "brief",
            "prompt",
            "icon",
            "tool_list",
            "source",
            "is_deleted",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_tool_list(self, value):
        return _normalize_string_list(value, "tool_list")

    def validate_source(self, value):
        return value or SmallTask.Source.SERVICE


class AdminAIProviderKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = AIProviderKeyConfig
        fields = (
            "id",
            "kind",
            "name",
            "company",
            "request_url",
            "is_hidden",
            "is_using",
            "capability_class",
            "help",
            "privacy_policy_url",
            "source",
            "position",
            "is_active",
            "updated_at",
            "created_at",
        )
        read_only_fields = ("id", "updated_at", "created_at")


class AdminAIProviderKeyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIProviderKeyConfig
        fields = (
            "kind",
            "name",
            "company",
            "key",
            "request_url",
            "is_hidden",
            "is_using",
            "capability_class",
            "help",
            "privacy_policy_url",
            "source",
            "position",
            "is_active",
        )


class AdminAIProviderKeyUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIProviderKeyConfig
        fields = (
            "key",
            "request_url",
            "is_hidden",
            "is_using",
            "capability_class",
            "help",
            "privacy_policy_url",
            "position",
            "is_active",
        )


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


class AdminTrialApplicationSerializer(serializers.ModelSerializer):
    applicant = serializers.CharField(source="user.username", read_only=True)
    applicant_email = serializers.CharField(source="user.email", read_only=True)
    latest_device = serializers.SerializerMethodField()
    application_requests = serializers.SerializerMethodField()

    class Meta:
        model = TrialApplication
        fields = (
            "id",
            "user",
            "applicant",
            "applicant_email",
            "status",
            "grant_source",
            "started_at",
            "expires_at",
            "applied_at",
            "approved_at",
            "rejected_at",
            "note",
            "latest_device",
            "application_requests",
            "created_at",
            "updated_at",
        )

    @staticmethod
    def _prefetched_latest_device(obj: TrialApplication) -> TrustedDevice | None:
        user = getattr(obj, "user", None)
        if user is None:
            return None
        cache = getattr(user, "_prefetched_objects_cache", None) or {}
        devices = cache.get("trusted_devices")
        if not devices:
            return None
        return devices[0]  # queryset already ordered in Prefetch

    @staticmethod
    def _fallback_latest_device(obj: TrialApplication) -> TrustedDevice | None:
        user_id = getattr(obj, "user_id", None)
        if not user_id:
            return None
        return (
            TrustedDevice.objects.filter(user_id=user_id)
            .order_by("-last_seen", "-id")
            .only(
                "id",
                "bundle_id",
                "device_id",
                "platform",
                "system_version",
                "device_model",
                "device_name",
                "language_code",
                "region_code",
                "country_code",
                "notifications_enabled",
                "is_revoked",
                "verified",
                "first_seen",
                "last_seen",
            )
            .first()
        )

    def get_latest_device(self, obj: TrialApplication):
        device = self._prefetched_latest_device(obj) or self._fallback_latest_device(obj)
        if device is None:
            return None
        return {
            "id": device.id,
            "bundle_id": device.bundle_id,
            "device_id": device.device_id,
            "platform": device.platform,
            "system_version": device.system_version,
            "device_model": device.device_model,
            "device_name": device.device_name,
            "language_code": device.language_code,
            "region_code": device.region_code,
            "country_code": device.country_code,
            "notifications_enabled": bool(device.notifications_enabled),
            "verified": bool(device.verified),
            "is_revoked": bool(device.is_revoked),
            "first_seen": device.first_seen,
            "last_seen": device.last_seen,
        }

    @staticmethod
    def _prefetched_requests(obj: TrialApplication) -> list[TrialApplicationRequest] | None:
        user = getattr(obj, "user", None)
        if user is None:
            return None
        cache = getattr(user, "_prefetched_objects_cache", None) or {}
        return cache.get("trial_application_requests")

    @staticmethod
    def _fallback_requests(obj: TrialApplication, limit: int = 20) -> list[TrialApplicationRequest]:
        user_id = getattr(obj, "user_id", None)
        if not user_id:
            return []
        return list(
            TrialApplicationRequest.objects.filter(user_id=user_id)
            .order_by("-created_at", "-id")
            .only(
                "id",
                "user_id",
                "source",
                "sequence",
                "status",
                "note",
                "auto_approve_after_seconds",
                "scheduled_at",
                "approved_at",
                "rejected_at",
                "created_at",
                "updated_at",
            )[:limit]
        )

    def get_application_requests(self, obj: TrialApplication):
        rows = self._prefetched_requests(obj)
        if rows is None:
            rows = self._fallback_requests(obj)
        if not rows:
            return []
        out = []
        for r in rows:
            out.append(
                {
                    "id": r.id,
                    "source": r.source,
                    "sequence": int(r.sequence or 0),
                    "status": r.status,
                    "note": r.note,
                    "auto_approve_after_seconds": r.auto_approve_after_seconds,
                    "scheduled_at": r.scheduled_at,
                    "approved_at": r.approved_at,
                    "rejected_at": r.rejected_at,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
            )
        return out


class AdminTrialActionSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)
    grant_days = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        action = (self.context.get("action") or "").strip().lower()
        if action == "grant":
            grant_days = attrs.get("grant_days")
            expires_at = attrs.get("expires_at")
            if grant_days is None and expires_at is None:
                raise serializers.ValidationError("grant_days 或 expires_at 至少提供一个")
        return attrs
