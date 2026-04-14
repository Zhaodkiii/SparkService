from django.contrib.auth import get_user_model
from rest_framework import serializers

from ai_config.models import AIModelCatalog, AIProviderKeyConfig, AIScenarioModelBinding, ScenarioKey, TrialApplication
from accounts.models import AccountDeactivation, AccountDeactivationAudit, NotificationCampaign, NotificationMessage, NotificationTemplate, TrustedDevice
from backoffice.models import AdminAuditLog, AdminPermission, AdminRole


User = get_user_model()


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


class AdminUserStatusSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()


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
            "endpoint",
            "provider_company",
            "provider_name",
            "temperature",
            "max_tokens",
            "position",
            "is_default",
            "is_active",
            "updated_at",
            "created_at",
        )
        read_only_fields = ("id", "scenario", "updated_at", "created_at")

    def _resolve_provider(self, obj: AIScenarioModelBinding):
        return _resolve_provider_for_catalog_model(obj.model)

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
        if scenario and self.instance is None:
            if not AIScenarioModelBinding.objects.filter(scenario=scenario).exists():
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
            "source",
            "is_active",
        )

    def validate_price_tier(self, value):
        return _validate_price_tier(value)


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
            "source",
            "is_active",
        )

    def validate_price_tier(self, value):
        return _validate_price_tier(value)


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
            "created_at",
            "updated_at",
        )


class AdminTrialActionSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)
