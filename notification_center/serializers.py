from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from notification_center.models import (
    ChannelDelivery,
    ContactEndpoint,
    NotificationBusinessScene,
    NotificationCampaign,
    NotificationIntent,
    NotificationMessage,
    NotificationSuppression,
    NotificationTemplate,
)
from notification_center.security import decrypt_sensitive


class NotificationBusinessSceneSerializer(serializers.ModelSerializer):
    topic_key = serializers.CharField(source="topic.key", read_only=True)
    topic_name = serializers.CharField(source="topic.name", read_only=True)

    class Meta:
        model = NotificationBusinessScene
        fields = (
            "id",
            "key",
            "display_name",
            "description",
            "domain",
            "business_type",
            "event_name",
            "topic",
            "topic_key",
            "topic_name",
            "category",
            "severity",
            "default_template_key",
            "default_routing",
            "variable_schema",
            "reference_schema",
            "client_action_schema",
            "idempotency_strategy",
            "dedupe_window_seconds",
            "preference_policy",
            "quiet_hour_policy",
            "retention_days",
            "status",
            "contract_version",
            "owner_team",
            "created_at",
            "updated_at",
        )


class NotificationIntentSerializer(serializers.ModelSerializer):
    recipient_count = serializers.IntegerField(read_only=True)
    message_count = serializers.IntegerField(read_only=True)
    delivery_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = NotificationIntent
        fields = (
            "id",
            "topic_key",
            "business_scene",
            "business_domain",
            "business_type",
            "business_reference_type",
            "business_id",
            "subject_type",
            "subject_id",
            "template_key",
            "routing",
            "scene_contract_version",
            "scene_snapshot",
            "event_id",
            "occurred_at",
            "actor_type",
            "actor_id",
            "idempotency_key",
            "trace_id",
            "source",
            "status",
            "priority",
            "scheduled_at",
            "expires_at",
            "recipient_count",
            "message_count",
            "delivery_count",
            "created_at",
            "updated_at",
        )


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = (
            "id",
            "key",
            "name",
            "description",
            "topic_key",
            "title_template",
            "body_template",
            "payload_template",
            "default_channels",
            "is_active",
            "created_at",
            "updated_at",
        )


class NotificationCampaignSerializer(serializers.ModelSerializer):
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


class NotificationMessageSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    recipient_key = serializers.SerializerMethodField()
    body = serializers.SerializerMethodField()
    payload = serializers.SerializerMethodField()
    delivery_details = serializers.SerializerMethodField()
    delivery_id = serializers.SerializerMethodField()
    business_type = serializers.SerializerMethodField()
    recipient_display = serializers.SerializerMethodField()
    account_identifier = serializers.SerializerMethodField()
    masked_phone = serializers.SerializerMethodField()
    template_code = serializers.SerializerMethodField()
    submit_status = serializers.SerializerMethodField()
    delivery_status = serializers.SerializerMethodField()
    code_err_code = serializers.SerializerMethodField()
    biz_id = serializers.SerializerMethodField()
    submitted_at = serializers.SerializerMethodField()
    receipt_at = serializers.SerializerMethodField()
    business_scene = serializers.SerializerMethodField()
    business_domain = serializers.SerializerMethodField()
    business_id = serializers.SerializerMethodField()

    def _latest_delivery(self, obj):
        cached = getattr(obj, "_latest_delivery_cached", None)
        if cached is not None:
            return cached
        delivery = (
            ChannelDelivery.objects.filter(message_id=obj.id)
            .order_by("-created_at", "-id")
            .first()
        )
        setattr(obj, "_latest_delivery_cached", delivery)
        return delivery

    def _resolved_sms_phone(self, obj):
        cached = getattr(obj, "_resolved_sms_phone_cached", None)
        if cached is not None:
            return cached
        phone_number = ""
        delivery = self._latest_delivery(obj)
        endpoint_hmac = ""
        if delivery and delivery.endpoint_hmac:
            endpoint_hmac = delivery.endpoint_hmac
        elif obj.recipient_key and len(obj.recipient_key) == 64:
            endpoint_hmac = obj.recipient_key
        if endpoint_hmac:
            endpoint = ContactEndpoint.objects.filter(channel=ContactEndpoint.Channel.SMS, address_hmac=endpoint_hmac).first()
            if endpoint is not None:
                phone_number = decrypt_sensitive(endpoint.address_ciphertext)
                if not phone_number:
                    phone_number = endpoint.address_masked
        if not phone_number:
            phone_number = obj.receiver_phone or ""
        setattr(obj, "_resolved_sms_phone_cached", phone_number)
        return phone_number

    def _resolved_sms_user(self, obj):
        cached = getattr(obj, "_resolved_sms_user_cached", None)
        if cached is not None:
            return cached
        resolved_user = getattr(obj, "user", None)
        setattr(obj, "_resolved_sms_user_cached", resolved_user)
        return resolved_user

    def _sms_delivery_details(self, obj) -> dict:
        delivery = self._latest_delivery(obj)
        if not delivery or not isinstance(delivery.details, dict):
            return {}
        return delivery.details or {}

    def _sms_submit_status_value(self, obj, delivery=None) -> str:
        delivery = delivery or self._latest_delivery(obj)
        details = delivery.details if delivery and isinstance(delivery.details, dict) else {}
        provider_code = (getattr(delivery, "provider_code", "") or obj.provider_code or details.get("code") or "").strip()
        provider_status = (getattr(delivery, "provider_status", "") or obj.provider_status or "").strip()
        biz_id = (getattr(delivery, "provider_message_id", "") or obj.provider_message_id or details.get("biz_id") or "").strip()
        error_code = (getattr(delivery, "error_code", "") or obj.error_message or "").strip()

        if provider_code == "OK" or provider_status in {"accepted", "submitted", "1", "2", "3"} or biz_id:
            return "accepted"
        if delivery and delivery.status == ChannelDelivery.Status.SUBMIT_UNKNOWN:
            return "unknown"
        if delivery and delivery.status == ChannelDelivery.Status.SUBMIT_FAILED:
            return "failed"
        if error_code:
            return "failed"
        return (getattr(delivery, "status", "") or obj.provider_status or obj.status or "").strip()

    def _sms_payload(self, obj) -> dict:
        details = self._sms_delivery_details(obj)
        template_param = details.get("template_param") if isinstance(details.get("template_param"), dict) else {}
        code = (template_param.get("code") or "").strip()
        if not code and isinstance(obj.payload, dict):
            code = str(obj.payload.get("code") or "").strip()
        return {"code": code} if code else {}

    def get_user_name(self, obj):
        resolved_user = self._resolved_sms_user(obj)
        if resolved_user is None:
            return ""
        return (resolved_user.username or "").strip()

    def get_recipient_key(self, obj):
        if obj.channel == NotificationMessage.Channel.SMS:
            return self._resolved_sms_phone(obj) or obj.recipient_key
        if obj.channel == NotificationMessage.Channel.EMAIL:
            return obj.receiver_email or "***"
        return "***"

    def get_body(self, obj):
        if obj.channel == NotificationMessage.Channel.SMS:
            return ""
        text = (obj.body or "").strip()
        if not text:
            return ""
        return text[:120] + ("..." if len(text) > 120 else "")

    def get_payload(self, obj):
        if obj.channel == NotificationMessage.Channel.SMS:
            return self._sms_payload(obj)
        if not isinstance(obj.payload, dict):
            return {}
        return obj.payload

    def get_delivery_details(self, obj):
        if obj.channel == NotificationMessage.Channel.SMS:
            delivery = self._latest_delivery(obj)
            if not delivery:
                return []
            details = self._sms_delivery_details(obj)
            return [
                {
                    "stage": "submit",
                    "status": self._sms_submit_status_value(obj, delivery),
                    "provider": delivery.provider or "aliyun",
                    "request_id": details.get("request_id") or delivery.provider_request_id or obj.provider_request_id or "",
                    "biz_id": details.get("biz_id") or delivery.provider_message_id or obj.provider_message_id or "",
                    "code": details.get("code") or delivery.provider_code or obj.provider_code or "",
                    "message": details.get("message") or "",
                    "template_code": details.get("template_code") or "",
                    "template_param_keys": details.get("template_param_keys") or [],
                    "template_param": details.get("template_param") or {},
                    "phone_number": self._resolved_sms_phone(obj),
                    "phone_number_masked": self._resolved_sms_phone(obj),
                    "accepted_at": delivery.accepted_at,
                },
                {
                    "stage": "receipt",
                    "status": self.get_delivery_status(obj),
                    "provider_status": delivery.provider_status or "",
                    "err_code": details.get("err_code") or delivery.error_code or "",
                    "receive_date": details.get("receive_date") or "",
                    "out_id": details.get("out_id") or "",
                    "delivered_at": delivery.delivered_at,
                    "error_message": delivery.error_message or "",
                },
            ]
        return obj.delivery_details or []

    def get_delivery_id(self, obj):
        delivery = self._latest_delivery(obj)
        return delivery.id if delivery else None

    def get_business_type(self, obj):
        if obj.intent_id and getattr(obj, "intent", None):
            return obj.intent.business_type or obj.intent.business_scene or obj.intent.topic_key or ""
        if obj.campaign_id and getattr(obj, "campaign", None):
            return obj.campaign.name or ""
        if obj.channel == NotificationMessage.Channel.SMS and obj.title == "验证码短信":
            return "login_otp"
        return ""

    def get_business_scene(self, obj):
        if obj.intent_id and getattr(obj, "intent", None):
            return obj.intent.business_scene or ""
        return ""

    def get_business_domain(self, obj):
        if obj.intent_id and getattr(obj, "intent", None):
            return obj.intent.business_domain or ""
        return ""

    def get_business_id(self, obj):
        if obj.intent_id and getattr(obj, "intent", None):
            return obj.intent.business_id or ""
        return ""

    def get_recipient_display(self, obj):
        resolved_user = self._resolved_sms_user(obj)
        if resolved_user is not None:
            username = getattr(resolved_user, "username", "") or ""
            return username or f"用户#{obj.user_id}"
        if obj.channel == NotificationMessage.Channel.SMS:
            return "登录前用户"
        return obj.recipient_type or "-"

    def get_account_identifier(self, obj):
        resolved_user = self._resolved_sms_user(obj)
        if resolved_user is not None:
            return getattr(resolved_user, "username", "") or str(resolved_user.id)
        if obj.channel == NotificationMessage.Channel.SMS:
            return self._resolved_sms_phone(obj) or obj.recipient_key or "-"
        if obj.channel == NotificationMessage.Channel.EMAIL:
            return obj.receiver_email or obj.recipient_key or "-"
        return obj.recipient_key or "-"

    def get_masked_phone(self, obj):
        return self._resolved_sms_phone(obj) if obj.channel == NotificationMessage.Channel.SMS else ""

    def get_template_code(self, obj):
        if obj.channel != NotificationMessage.Channel.SMS:
            return ""
        delivery = self._latest_delivery(obj)
        details = delivery.details if delivery and isinstance(delivery.details, dict) else {}
        return str(details.get("template_code") or "")

    def get_submit_status(self, obj):
        delivery = self._latest_delivery(obj)
        if not delivery:
            return obj.provider_status or obj.status
        return self._sms_submit_status_value(obj, delivery)

    def get_delivery_status(self, obj):
        delivery = self._latest_delivery(obj)
        if not delivery:
            return "unknown" if obj.status == NotificationMessage.Status.SENT and not obj.delivered_at else obj.status
        if delivery.status == ChannelDelivery.Status.DELIVERED:
            return "delivered"
        if delivery.status == ChannelDelivery.Status.DELIVERY_FAILED:
            return "failed"
        if delivery.status in {ChannelDelivery.Status.ACCEPTED, ChannelDelivery.Status.SUBMITTED}:
            return "pending"
        if delivery.status == ChannelDelivery.Status.SUBMIT_UNKNOWN:
            return "unknown"
        return delivery.status

    def get_code_err_code(self, obj):
        delivery = self._latest_delivery(obj)
        if delivery:
            return delivery.error_code or delivery.provider_code or ""
        return obj.provider_code or ""

    def get_biz_id(self, obj):
        return obj.provider_message_id or ""

    def get_submitted_at(self, obj):
        delivery = self._latest_delivery(obj)
        return delivery.accepted_at if delivery and delivery.accepted_at else obj.sent_at

    def get_receipt_at(self, obj):
        delivery = self._latest_delivery(obj)
        return delivery.delivered_at if delivery and delivery.delivered_at else obj.delivered_at

    class Meta:
        model = NotificationMessage
        fields = (
            "id",
            "delivery_id",
            "business_scene",
            "business_domain",
            "business_type",
            "business_id",
            "campaign",
            "campaign_name",
            "user",
            "user_name",
            "recipient_type",
            "recipient_display",
            "account_identifier",
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
            "masked_phone",
            "apns_topic",
            "template_code",
            "submit_status",
            "delivery_status",
            "code_err_code",
            "biz_id",
            "provider_message_id",
            "provider_request_id",
            "provider_code",
            "provider_status",
            "error_message",
            "request_id",
            "submitted_at",
            "receipt_at",
            "sent_at",
            "delivered_at",
            "created_at",
            "updated_at",
        )


class NotificationSuppressionSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = NotificationSuppression
        fields = (
            "id",
            "endpoint_hmac",
            "user",
            "user_name",
            "channel",
            "reason",
            "detail",
            "expires_at",
            "created_by",
            "created_by_name",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_by",)

    def get_is_active(self, obj: NotificationSuppression) -> bool:
        return obj.expires_at is None or obj.expires_at > timezone.now()
