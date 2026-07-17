from __future__ import annotations

import json
import math
import logging
import time as time_module
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.template.loader import render_to_string
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from accounts.infrastructure.apns_provider import APNsProvider
from accounts.infrastructure.email_provider import EmailProvider
from accounts.infrastructure.sms_provider import AliyunSMSProvider
from accounts.models import AccountDeviceSession, PhoneOTP, SocialIdentity, TrustedDevice
from accounts.services.device_session_service import DeviceSessionService
from accounts.services.phone_number_service import PhoneNumberService
from notification_center.models import (
    AudienceDefinition,
    AudienceSnapshot,
    ChannelDelivery,
    ContactEndpoint,
    DeliveryAttempt,
    NotificationBusinessScene,
    NotificationAuditLog,
    NotificationCampaign,
    NotificationIntent,
    NotificationMessage,
    NotificationOutbox,
    NotificationPreference,
    NotificationRecipientMessage,
    NotificationSuppression,
    NotificationTemplate,
    NotificationTemplateVersion,
    ProviderEvent,
    NotificationTopic,
)
from notification_center.security import decrypt_sensitive, encrypt_sensitive, keyed_hmac

try:
    from notification_center.business_scenes import MEMBERSHIP_USER_NOTIFICATION_SUPPRESSED_SCENES
except ImportError:  # pragma: no cover
    MEMBERSHIP_USER_NOTIFICATION_SUPPRESSED_SCENES = frozenset()

logger = logging.getLogger(__name__)
User = get_user_model()

_EXTERNAL_DELIVERY_CHANNELS = frozenset(
    {
        NotificationMessage.Channel.APNS,
        NotificationMessage.Channel.EMAIL,
        NotificationMessage.Channel.SMS,
    }
)


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _mask_phone(phone_number: str) -> str:
    phone = "".join(ch for ch in (phone_number or "") if ch.isdigit())
    if not phone:
        return ""
    if len(phone) <= 4:
        return "***"
    return f"{phone[:3]}****{phone[-4:]}"


def _mask_email(email: str) -> str:
    value = (email or "").strip()
    if not value:
        return ""
    if "@" not in value:
        return "***"
    local, _, domain = value.partition("@")
    if len(local) <= 1:
        return f"*@{domain}"
    if len(local) <= 4:
        return f"{local[0]}***@{domain}"
    return f"{local[:3]}***@{domain}"


def _coerce_positive_int(value, *, default: int, maximum: int | None = None) -> int:
    try:
        parsed = max(int(value or default), 1)
    except (TypeError, ValueError):
        parsed = default
    if maximum is not None:
        return min(parsed, maximum)
    return parsed


def _coerce_bool(value, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return default


def _coerce_optional_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


@dataclass(frozen=True)
class _SendResult:
    accepted: bool
    delivered: bool
    unknown: bool
    skipped: bool
    reason: str
    provider_message_id: str
    provider_request_id: str = ""
    provider_code: str = ""
    provider_status: str = ""
    provider_payload: dict[str, Any] | None = None
    occurred_at: datetime | None = None


_BUILTIN_BUSINESS_SCENES: dict[str, dict[str, Any]] = {
    "account.auth.registration_otp_requested": {
        "display_name": "注册验证码",
        "description": "注册手机号或邮箱验证挑战创建时使用。",
        "category": NotificationBusinessScene.Category.SECURITY,
        "severity": NotificationBusinessScene.Severity.INFO,
        "default_template_key": "account_auth_registration_otp",
        "default_routing": {"mode": "parallel", "steps": [{"channel": "sms", "required": True, "success_threshold": "provider_accepted"}]},
        "preference_policy": "mandatory",
        "quiet_hour_policy": "bypass_critical",
        "status": NotificationBusinessScene.Status.ACTIVE,
        "contract_version": 1,
    },
    "account.auth.login_otp_requested": {
        "display_name": "登录验证码",
        "description": "登录挑战创建时使用。",
        "category": NotificationBusinessScene.Category.SECURITY,
        "severity": NotificationBusinessScene.Severity.INFO,
        "default_template_key": "account_auth_login_otp",
        "default_routing": {"mode": "parallel", "steps": [{"channel": "sms", "required": True, "success_threshold": "provider_accepted"}]},
        "preference_policy": "mandatory",
        "quiet_hour_policy": "bypass_critical",
        "status": NotificationBusinessScene.Status.ACTIVE,
        "contract_version": 1,
    },
    "account.lifecycle.deactivation_requested": {
        "display_name": "注销申请已受理",
        "description": "用户提交账号注销请求后使用。",
        "category": NotificationBusinessScene.Category.TRANSACTIONAL,
        "severity": NotificationBusinessScene.Severity.WARNING,
        "default_template_key": "account_lifecycle_deactivation_requested",
        "default_routing": {"mode": "parallel", "steps": [{"channel": "in_app", "required": False}, {"channel": "email", "required": False}, {"channel": "sms", "required": False}]},
        "preference_policy": "mandatory",
        "quiet_hour_policy": "bypass_critical",
        "status": NotificationBusinessScene.Status.ACTIVE,
        "contract_version": 1,
    },
    "account.lifecycle.deactivation_completed": {
        "display_name": "注销完成",
        "description": "账号注销终态完成后使用。",
        "category": NotificationBusinessScene.Category.TRANSACTIONAL,
        "severity": NotificationBusinessScene.Severity.CRITICAL,
        "default_template_key": "account_lifecycle_deactivation_completed",
        "default_routing": {"mode": "parallel", "steps": [{"channel": "email", "required": False}, {"channel": "sms", "required": False}, {"channel": "in_app", "required": False}]},
        "preference_policy": "mandatory",
        "quiet_hour_policy": "bypass_critical",
        "status": NotificationBusinessScene.Status.ACTIVE,
        "contract_version": 1,
    },
    "operation.campaign.published": {
        "display_name": "运营活动发布",
        "description": "后台活动或公告发布时使用。",
        "category": NotificationBusinessScene.Category.OPERATIONAL,
        "severity": NotificationBusinessScene.Severity.INFO,
        "default_template_key": "operation_campaign_published",
        "default_routing": {"mode": "parallel", "steps": [{"channel": "apns", "required": False}, {"channel": "email", "required": False}, {"channel": "sms", "required": False}]},
        "preference_policy": "opt_out",
        "quiet_hour_policy": "respect",
        "status": NotificationBusinessScene.Status.ACTIVE,
        "contract_version": 1,
    },
}

_BUSINESS_SCENE_ALIASES = {
    "login": "account.auth.login_otp_requested",
    "registration": "account.auth.registration_otp_requested",
    "register": "account.auth.registration_otp_requested",
    "identity_bind": "account.auth.identity_bind_otp_requested",
    "identity_change": "account.auth.identity_change_otp_requested",
    "identity_reauth": "account.auth.identity_reauth_otp_requested",
    "account_deactivation": "account.lifecycle.deactivation_requested",
    "deactivation": "account.lifecycle.deactivation_requested",
    "campaign": "operation.campaign.published",
}


class NotificationCenterService:
    @staticmethod
    def _normalize_scene_key(scene_key: str) -> str:
        normalized = (scene_key or "").strip().lower().replace(" ", "_")
        return _BUSINESS_SCENE_ALIASES.get(normalized, normalized)

    @staticmethod
    def _scene_display_name_from_key(scene_key: str) -> str:
        normalized = NotificationCenterService._normalize_scene_key(scene_key)
        default = _BUILTIN_BUSINESS_SCENES.get(normalized, {})
        if default.get("display_name"):
            return str(default["display_name"])
        parts = [part for part in normalized.split(".") if part]
        if not parts:
            return "未知场景"
        return " / ".join(parts)

    @staticmethod
    def _scene_category_for_key(scene_key: str) -> str:
        normalized = NotificationCenterService._normalize_scene_key(scene_key)
        default = _BUILTIN_BUSINESS_SCENES.get(normalized, {})
        if default.get("category"):
            return str(default["category"])
        if normalized.startswith("account."):
            return NotificationBusinessScene.Category.SECURITY
        if normalized.startswith("medical.") or normalized.startswith("task."):
            return NotificationBusinessScene.Category.TRANSACTIONAL
        if normalized.startswith("operation.") or normalized.startswith("content."):
            return NotificationBusinessScene.Category.OPERATIONAL
        if normalized.startswith("system."):
            return NotificationBusinessScene.Category.SYSTEM
        return NotificationBusinessScene.Category.TRANSACTIONAL

    @staticmethod
    def _scene_severity_for_key(scene_key: str) -> str:
        normalized = NotificationCenterService._normalize_scene_key(scene_key)
        default = _BUILTIN_BUSINESS_SCENES.get(normalized, {})
        if default.get("severity"):
            return str(default["severity"])
        if normalized.endswith("failed"):
            return NotificationBusinessScene.Severity.WARNING
        return NotificationBusinessScene.Severity.INFO

    @staticmethod
    def ensure_business_scene(scene_key: str, *, topic_key: str = "", display_name: str = "", description: str = "") -> NotificationBusinessScene:
        normalized_key = NotificationCenterService._normalize_scene_key(scene_key)
        if not normalized_key:
            raise ValueError("business_scene_required")
        from notification_center.business_scenes import SCENE_BY_KEY

        scene = NotificationBusinessScene.objects.filter(key=normalized_key).first()
        if scene is None:
            definition = SCENE_BY_KEY.get(normalized_key)
            if definition is None:
                raise ValueError("business_scene_not_registered")
            topic = NotificationTopic.objects.filter(key=topic_key or definition.topic_key).first()
            scene = NotificationBusinessScene.objects.create(**definition.defaults(topic))
        if scene.status != NotificationBusinessScene.Status.ACTIVE:
            raise ValueError("business_scene_not_active")
        return scene

    @staticmethod
    def _scene_parts(scene_key: str) -> tuple[str, str, str]:
        normalized_key = NotificationCenterService._normalize_scene_key(scene_key)
        parts = [part for part in normalized_key.split(".") if part]
        if not parts:
            return "", "", ""
        if len(parts) == 1:
            return parts[0], parts[0], parts[0]
        if len(parts) == 2:
            return parts[0], ".".join(parts), parts[-1]
        domain = parts[0]
        event_name = parts[-1]
        business_type = ".".join(parts[:2])
        return domain, business_type, event_name

    @staticmethod
    def _scene_snapshot(scene: NotificationBusinessScene) -> dict[str, Any]:
        return {
            "key": scene.key,
            "display_name": scene.display_name,
            "category": scene.category,
            "severity": scene.severity,
            "contract_version": scene.contract_version,
            "default_template_key": scene.default_template_key,
            "default_routing": scene.default_routing,
            "status": scene.status,
        }

    @staticmethod
    def _email_otp_context(*, email: str, code: str, expires_at, request_id: str = "") -> dict[str, Any]:
        now = timezone.now()
        expiry_at = expires_at or (now + timedelta(minutes=5))
        expires_in_seconds = max(0, int((expiry_at - now).total_seconds()))
        expires_in_minutes = max(1, math.ceil(expires_in_seconds / 60))
        return {
            "brand_name": "DreamWhale",
            "subject": "【DreamWhale】您的账号安全验证码",
            "email": email,
            "code": code,
            "expires_at": expiry_at,
            "expires_minutes": expires_in_minutes,
            "support_url": "https://dreamwhale.top",
            "request_id": request_id,
        }

    @staticmethod
    def _render_email_otp_text(context: dict[str, Any]) -> str:
        return render_to_string("notification_center/email_otp.txt", context)

    @staticmethod
    def _render_email_otp_html(context: dict[str, Any]) -> str:
        return render_to_string("notification_center/email_otp.html", context)

    @staticmethod
    def _build_intent_scene_context(
        *,
        scene: NotificationBusinessScene,
        business_reference_type: str = "",
        business_id: str = "",
        subject_type: str = "",
        subject_id: str = "",
        actor_type: str = "",
        actor_id: str = "",
    ) -> dict[str, str]:
        return {
            "scene": scene.key,
            "business_domain": scene.domain,
            "business_type": scene.business_type,
            "business_reference_type": (business_reference_type or "").strip(),
            "business_id": (business_id or "").strip(),
            "subject_type": (subject_type or "").strip(),
            "subject_id": (subject_id or "").strip(),
            "actor_type": (actor_type or "").strip(),
            "actor_id": (actor_id or "").strip(),
        }

    @staticmethod
    def _phone_identity_queryset():
        return SocialIdentity.objects.filter(provider=SocialIdentity.Provider.PHONE).exclude(provider_uid="")

    @staticmethod
    def _phone_number_for_user(user: User) -> str:
        identity = NotificationCenterService._phone_identity_queryset().filter(user_id=user.id).first()
        return (identity.provider_uid if identity else "") or ""

    @staticmethod
    def _normalize_phone(phone_number: str) -> str:
        return PhoneNumberService.normalize_e164(phone_number)

    @staticmethod
    def _phone_hmac(phone_number: str) -> str:
        normalized = NotificationCenterService._normalize_phone(phone_number)
        return keyed_hmac(normalized, scope="phone")

    @staticmethod
    def _sms_receipt_query_phone(phone_number: str) -> str:
        normalized = NotificationCenterService._normalize_phone(phone_number)
        digits = normalized.lstrip("+")
        if digits.startswith("86") and len(digits) == 13:
            return digits[2:]
        return digits or normalized.lstrip("+")

    @staticmethod
    def _sms_receipt_query_send_date(delivery: ChannelDelivery) -> datetime:
        source_time = None
        if getattr(delivery, "message", None) and delivery.message.sent_at:
            source_time = delivery.message.sent_at
        elif delivery.accepted_at:
            source_time = delivery.accepted_at
        elif getattr(delivery, "message", None) and delivery.message.created_at:
            source_time = delivery.message.created_at
        else:
            source_time = delivery.created_at

        if timezone.is_naive(source_time):
            source_time = timezone.make_aware(source_time, timezone=timezone.get_current_timezone())
        return timezone.localtime(source_time, timezone=ZoneInfo("Asia/Shanghai"))

    @staticmethod
    def _email_hmac(email: str) -> str:
        normalized = (email or "").strip()
        if "@" not in normalized:
            return keyed_hmac(normalized.lower(), scope="email")
        local, _, domain = normalized.partition("@")
        return keyed_hmac(f"{local}@{domain.lower()}", scope="email")

    @staticmethod
    def build_context_for_user(user: User) -> dict[str, str]:
        now = timezone.localtime()
        return {
            "user_id": str(user.id),
            "username": user.username or "",
            "email": (user.email or "").strip(),
            "phone": NotificationCenterService._phone_number_for_user(user),
            "date": now.strftime("%Y-%m-%d"),
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        }

    @staticmethod
    def render_text(template_text: str, context: dict[str, str]) -> str:
        return (template_text or "").format_map(_SafeDict(context))

    @staticmethod
    def build_message_content(
        *,
        user: User,
        template: NotificationTemplate | None,
        template_version: NotificationTemplateVersion | None = None,
        title: str,
        body: str,
        payload: dict | None,
    ):
        context = NotificationCenterService.build_context_for_user(user)
        raw_title = (
            (template_version.title_template if template_version else "")
            or (template.title_template if template else "")
            or title
            or ""
        )
        raw_body = (
            (template_version.body_template if template_version else "")
            or (template.body_template if template else "")
            or body
            or ""
        )
        title_rendered = NotificationCenterService.render_text(raw_title, context)
        body_rendered = NotificationCenterService.render_text(raw_body, context)

        payload_source = template_version.payload_template if template_version else (template.payload_template if template else {})
        payload_rendered = dict(payload_source) if isinstance(payload_source, dict) else {}
        if payload:
            payload_rendered.update(payload)
        return title_rendered, body_rendered, payload_rendered

    @staticmethod
    def list_templates() -> list[NotificationTemplate]:
        return list(NotificationTemplate.objects.order_by("-is_active", "name", "id"))

    @staticmethod
    def publish_template_snapshot(*, template: NotificationTemplate, created_by_id: int | None = None) -> NotificationTemplateVersion:
        latest = template.versions.order_by("-version").first()
        version_no = 1 if latest is None else latest.version + 1
        row = NotificationTemplateVersion.objects.create(
            template=template,
            version=version_no,
            locale="zh-CN",
            status=NotificationTemplateVersion.Status.PUBLISHED,
            title_template=template.title_template,
            body_template=template.body_template,
            payload_template=template.payload_template if isinstance(template.payload_template, dict) else {},
            payload_schema=template.payload_template if isinstance(template.payload_template, dict) else {},
            created_by_id=created_by_id,
            published_at=timezone.now(),
        )
        template.updated_by_id = created_by_id
        template.save(update_fields=["updated_by", "updated_at"])
        return row

    @staticmethod
    def get_overview(*, window_days: int = 7) -> dict[str, Any]:
        window_days = max(1, min(int(window_days or 7), 30))
        since = timezone.now() - timedelta(days=window_days)
        messages = NotificationMessage.objects.filter(created_at__gte=since)
        deliveries = ChannelDelivery.objects.filter(created_at__gte=since)

        message_agg = messages.aggregate(
            total=Count("id"),
            sent=Count("id", filter=Q(status=NotificationMessage.Status.SENT)),
            failed=Count("id", filter=Q(status=NotificationMessage.Status.FAILED)),
            partial=Count("id", filter=Q(status=NotificationMessage.Status.PARTIAL)),
            skipped=Count("id", filter=Q(status=NotificationMessage.Status.SKIPPED)),
        )
        delivery_agg = deliveries.aggregate(
            total=Count("id"),
            delivered=Count("id", filter=Q(status=ChannelDelivery.Status.DELIVERED)),
            accepted=Count("id", filter=Q(status=ChannelDelivery.Status.ACCEPTED)),
            delivery_failed=Count("id", filter=Q(status=ChannelDelivery.Status.DELIVERY_FAILED)),
            submit_failed=Count("id", filter=Q(status=ChannelDelivery.Status.SUBMIT_FAILED)),
            submit_unknown=Count("id", filter=Q(status=ChannelDelivery.Status.SUBMIT_UNKNOWN)),
            cancelled=Count("id", filter=Q(status=ChannelDelivery.Status.CANCELLED)),
            expired=Count("id", filter=Q(status=ChannelDelivery.Status.EXPIRED)),
        )
        by_channel = {}
        for channel in [NotificationMessage.Channel.APNS, NotificationMessage.Channel.EMAIL, NotificationMessage.Channel.SMS]:
            channel_messages = messages.filter(channel=channel)
            channel_deliveries = deliveries.filter(channel=channel)
            by_channel[channel] = {
                "messages": channel_messages.count(),
                "deliveries": channel_deliveries.count(),
                "delivered": channel_deliveries.filter(status=ChannelDelivery.Status.DELIVERED).count(),
                "failed": channel_deliveries.filter(status=ChannelDelivery.Status.DELIVERY_FAILED).count(),
            }

        recent_messages = list(
            messages.select_related("user", "campaign")
            .order_by("-created_at", "-id")
            .values(
                "id",
                "campaign_id",
                "channel",
                "status",
                "title",
                "receiver_email",
                "receiver_phone",
                "request_id",
                "created_at",
            )[:10]
        )
        recent_messages_out = []
        for row in recent_messages:
            recipient = row.get("receiver_phone") or row.get("receiver_email") or "-"
            recent_messages_out.append(
                {
                    "id": row["id"],
                    "campaign_id": row["campaign_id"],
                    "channel": row["channel"],
                    "status": row["status"],
                    "title": row["title"],
                    "recipient": recipient,
                    "request_id": row["request_id"],
                    "created_at": row["created_at"],
                }
            )

        return {
            "window_days": window_days,
            "since": since,
            "summary": {
                "message_total": int(message_agg.get("total") or 0),
                "message_sent": int(message_agg.get("sent") or 0),
                "message_failed": int(message_agg.get("failed") or 0),
                "message_partial": int(message_agg.get("partial") or 0),
                "message_skipped": int(message_agg.get("skipped") or 0),
                "delivery_total": int(delivery_agg.get("total") or 0),
                "delivery_delivered": int(delivery_agg.get("delivered") or 0),
                "delivery_accepted": int(delivery_agg.get("accepted") or 0),
                "delivery_failed": int(delivery_agg.get("delivery_failed") or 0),
                "delivery_submit_failed": int(delivery_agg.get("submit_failed") or 0),
                "delivery_submit_unknown": int(delivery_agg.get("submit_unknown") or 0),
                "delivery_cancelled": int(delivery_agg.get("cancelled") or 0),
                "delivery_expired": int(delivery_agg.get("expired") or 0),
            },
            "by_channel": by_channel,
            "recent_messages": recent_messages_out,
        }

    @staticmethod
    def _q_user_has_apns_notification_allowed() -> Q:
        return Q(
            device_sessions__status=AccountDeviceSession.Status.ACTIVE,
            device_sessions__trusted_device__notifications_enabled=True,
        )

    @staticmethod
    def _q_user_has_push_capable_apns() -> Q:
        return Q(
            device_sessions__status=AccountDeviceSession.Status.ACTIVE,
            device_sessions__trusted_device__notifications_enabled=True,
            device_sessions__trusted_device__push_token__isnull=False,
        ) & ~Q(device_sessions__trusted_device__push_token="")

    @staticmethod
    def _q_user_has_email_channel() -> Q:
        return Q(email__isnull=False) & ~Q(email="")

    @staticmethod
    def _q_user_has_sms_channel() -> Q:
        return Q(
            social_identities__provider=SocialIdentity.Provider.PHONE,
            social_identities__provider_uid__gt="",
        )

    @staticmethod
    def _q_user_has_any_notifiable_channel() -> Q:
        return (
            NotificationCenterService._q_user_has_apns_notification_allowed()
            | NotificationCenterService._q_user_has_email_channel()
            | NotificationCenterService._q_user_has_sms_channel()
        )

    @staticmethod
    def _filter_user_queryset(
        *,
        q: str = "",
        only_enabled: bool = True,
        has_email: bool | None = None,
        has_sms: bool | None = None,
        has_apns: bool | None = None,
        is_active: bool | None = None,
    ):
        queryset = User.objects.all().order_by("-date_joined", "-id")
        if q:
            q_stripped = q.strip()
            search_q = Q(username__icontains=q_stripped) | Q(email__icontains=q_stripped) | Q(
                social_identities__provider=SocialIdentity.Provider.PHONE,
                social_identities__provider_uid__icontains=q_stripped,
            )
            if q_stripped.isdigit():
                search_q |= Q(id=int(q_stripped))
            queryset = queryset.filter(search_q)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if has_email is True:
            queryset = queryset.exclude(email="").filter(email__isnull=False)
        elif has_email is False:
            queryset = queryset.filter(Q(email="") | Q(email__isnull=True))

        if has_sms is True:
            queryset = queryset.filter(social_identities__provider=SocialIdentity.Provider.PHONE).exclude(social_identities__provider_uid="")
        elif has_sms is False:
            queryset = queryset.exclude(id__in=NotificationCenterService._phone_identity_queryset().values("user_id"))

        if has_apns is True:
            queryset = queryset.filter(NotificationCenterService._q_user_has_push_capable_apns())
        elif has_apns is False:
            queryset = queryset.exclude(NotificationCenterService._q_user_has_push_capable_apns())

        if only_enabled:
            queryset = queryset.filter(NotificationCenterService._q_user_has_any_notifiable_channel())

        return queryset.distinct()

    @staticmethod
    def list_notification_users(*, q: str = "", page: int = 1, page_size: int = 20, only_enabled: bool = True, has_email: bool | None = None, has_sms: bool | None = None, has_apns: bool | None = None, is_active: bool | None = None) -> dict[str, Any]:
        page = _coerce_positive_int(page, default=1)
        page_size = _coerce_positive_int(page_size, default=20, maximum=100)
        only_enabled = _coerce_bool(only_enabled, default=True)
        has_email = _coerce_optional_bool(has_email)
        has_sms = _coerce_optional_bool(has_sms)
        has_apns = _coerce_optional_bool(has_apns)
        is_active = _coerce_optional_bool(is_active)

        queryset = NotificationCenterService._filter_user_queryset(
            q=q,
            only_enabled=only_enabled,
            has_email=has_email,
            has_sms=has_sms,
            has_apns=has_apns,
            is_active=is_active,
        )
        total = queryset.count()
        offset = max(page - 1, 0) * page_size
        rows = list(queryset[offset : offset + page_size])
        user_ids = [u.id for u in rows]

        phone_identities = {
            identity.user_id: identity.provider_uid
            for identity in NotificationCenterService._phone_identity_queryset().filter(user_id__in=user_ids)
        }
        stats_map: dict[int, dict[str, int]] = {}
        active_sessions = (
            AccountDeviceSession.objects.filter(
                user_id__in=user_ids,
                status=AccountDeviceSession.Status.ACTIVE,
            )
            .select_related("trusted_device")
        )
        for session in active_sessions:
            device = session.trusted_device
            if device is None:
                continue
            has_push = bool((device.push_token or "").strip())
            stats_map[session.user_id] = {
                "total_devices": 1,
                "notifications_enabled_devices": 1 if device.notifications_enabled else 0,
                "enabled_push_devices": 1 if device.notifications_enabled and has_push else 0,
            }

        items = []
        for user in rows:
            stat = stats_map.get(user.id, {"total_devices": 0, "notifications_enabled_devices": 0, "enabled_push_devices": 0})
            phone = phone_identities.get(user.id, "") or ""
            email = (user.email or "").strip()
            notifications_enabled_devices = int(stat.get("notifications_enabled_devices") or 0)
            enabled_push_devices = int(stat.get("enabled_push_devices") or 0)
            items.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "email": email,
                    "phone_number": phone,
                    "is_active": user.is_active,
                    "date_joined": user.date_joined,
                    "last_login": user.last_login,
                    "total_devices": int(stat.get("total_devices") or 0),
                    "enabled_push_devices": enabled_push_devices,
                    "channels": {
                        "apns": notifications_enabled_devices > 0,
                        "email": bool(email),
                        "sms": bool(phone),
                    },
                }
            )

        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
            },
        }

    @staticmethod
    def resolve_target_user_ids(*, user_id: int | None = None, user_ids: list[int] | None = None, filters: dict | None = None) -> list[int]:
        if user_id:
            return [int(user_id)]
        if user_ids:
            return sorted({int(i) for i in user_ids if i})

        filters = filters or {}
        queryset = NotificationCenterService._filter_user_queryset(
            q=(filters.get("q") or "").strip(),
            only_enabled=bool(filters.get("only_enabled", False)),
            has_email=filters.get("has_email"),
            has_sms=filters.get("has_sms"),
            has_apns=filters.get("has_apns"),
            is_active=filters.get("is_active"),
        )
        return list(queryset.values_list("id", flat=True))

    @staticmethod
    def _resolve_delivery_state(result: _SendResult) -> tuple[str, str]:
        if result.skipped:
            return NotificationMessage.Status.SKIPPED, ChannelDelivery.Status.CANCELLED
        if result.delivered:
            return NotificationMessage.Status.DELIVERED, ChannelDelivery.Status.DELIVERED
        if result.accepted:
            return NotificationMessage.Status.ACCEPTED, ChannelDelivery.Status.ACCEPTED
        if result.unknown:
            return NotificationMessage.Status.PROCESSING, ChannelDelivery.Status.SUBMIT_UNKNOWN
        return NotificationMessage.Status.FAILED, ChannelDelivery.Status.SUBMIT_FAILED

    @staticmethod
    def _provider_event_type(result: _SendResult) -> str:
        if result.delivered:
            return ProviderEvent.NormalizedType.DELIVERED
        if result.accepted:
            return ProviderEvent.NormalizedType.SUBMITTED
        if result.unknown:
            return ProviderEvent.NormalizedType.UNKNOWN
        return ProviderEvent.NormalizedType.DELIVERY_FAILED

    @staticmethod
    def _is_quiet_hours(quiet_hours: dict[str, Any] | None) -> bool:
        cfg = quiet_hours or {}
        start_text = str(cfg.get("start") or "").strip()
        end_text = str(cfg.get("end") or "").strip()
        if not start_text or not end_text:
            return False
        tz_name = str(cfg.get("timezone") or timezone.get_current_timezone_name()).strip() or timezone.get_current_timezone_name()
        try:
            hour_start, minute_start = [int(part) for part in start_text.split(":", 1)]
            hour_end, minute_end = [int(part) for part in end_text.split(":", 1)]
            try:
                zone = ZoneInfo(tz_name)
                now_local = timezone.localtime(timezone.now(), timezone=zone)
            except Exception:  # noqa: BLE001
                now_local = timezone.localtime()
            current = now_local.time()
            start_at = time(hour_start, minute_start)
            end_at = time(hour_end, minute_end)
        except Exception:  # noqa: BLE001
            return False
        if start_at <= end_at:
            return start_at <= current <= end_at
        return current >= start_at or current <= end_at

    @staticmethod
    def _suppression_reason(*, user: User | None, channel: str, topic_key: str, endpoint_hmac: str = "") -> str:
        now = timezone.now()
        suppression = NotificationSuppression.objects.filter(
            Q(user=user) | (Q(user__isnull=True) & Q(endpoint_hmac=endpoint_hmac)),
            Q(channel=channel) | Q(channel=NotificationSuppression.Channel.ALL),
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).order_by("-created_at").first()
        if suppression:
            return suppression.reason
        if user is None:
            return ""
        preference = NotificationPreference.objects.filter(user=user, topic_key=topic_key, channel=channel).first()
        if preference and not preference.enabled:
            return "topic_opt_out"
        if preference and NotificationCenterService._is_quiet_hours(preference.quiet_hours):
            return "quiet_hours"
        return ""

    @staticmethod
    def _existing_message(*, campaign_id: int | None, recipient_key: str, channel: str, request_id: str) -> NotificationMessage | None:
        if not request_id:
            return None
        return (
            NotificationMessage.objects.filter(
                campaign_id=campaign_id,
                recipient_key=recipient_key,
                channel=channel,
                request_id=request_id,
            )
            .order_by("-id")
            .first()
        )

    @staticmethod
    def _route_steps(*, channels: list[str], routing: dict[str, Any] | None = None) -> tuple[str, list[dict[str, Any]]]:
        routing_cfg = routing or {}
        mode = str(routing_cfg.get("mode") or "parallel").strip() or "parallel"
        raw_steps = routing_cfg.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raw_steps = [{"channel": channel, "required": True, "success_threshold": "provider_accepted"} for channel in channels]
        steps: list[dict[str, Any]] = []
        for index, raw_step in enumerate(raw_steps, start=1):
            if isinstance(raw_step, str):
                steps.append({"channel": raw_step, "required": True, "route_order": index, "success_threshold": "provider_accepted"})
                continue
            channel = str((raw_step or {}).get("channel") or "").strip()
            if not channel:
                continue
            steps.append(
                {
                    "channel": channel,
                    "required": bool((raw_step or {}).get("required", True)),
                    "route_order": int((raw_step or {}).get("route_order") or index),
                    "success_threshold": str((raw_step or {}).get("success_threshold") or "provider_accepted"),
                }
            )
        return mode, steps

    @staticmethod
    def _route_channels_from_steps(steps: list[dict[str, Any]]) -> list[str]:
        channels: list[str] = []
        for step in steps:
            channel = str(step.get("channel") or "").strip()
            if channel and channel not in channels:
                channels.append(channel)
        return channels

    @staticmethod
    def _resolve_send_routing(
        *,
        channels: list[str],
        routing: dict[str, Any] | None,
        business_scene: str = "",
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        resolved_mode, resolved_steps = NotificationCenterService._route_steps(channels=[], routing=routing)
        if resolved_steps:
            resolved_channels = NotificationCenterService._route_channels_from_steps(resolved_steps)
            if channels and set(channels) != set(resolved_channels):
                logger.warning(
                    "notification.route.channels_overridden scene=%s input_channels=%s resolved_channels=%s",
                    business_scene or "-",
                    ",".join(channels),
                    ",".join(resolved_channels),
                )
            return resolved_mode, resolved_steps, resolved_channels
        mode, steps = NotificationCenterService._route_steps(channels=channels, routing=routing)
        return mode, steps, NotificationCenterService._route_channels_from_steps(steps) or list(channels)

    @staticmethod
    def _should_continue_fallback(*, mode: str, delivery: ChannelDelivery | None, step: dict[str, Any]) -> bool:
        if mode != "fallback":
            return True
        if delivery is None:
            return True
        threshold = str(step.get("success_threshold") or "provider_accepted")
        if NotificationCenterService._delivery_meets_threshold(delivery, threshold):
            return False
        if delivery.status in {
            ChannelDelivery.Status.SUBMIT_UNKNOWN,
            ChannelDelivery.Status.PROCESSING,
            ChannelDelivery.Status.QUEUED,
            ChannelDelivery.Status.CREATED,
        }:
            return False
        return True

    @staticmethod
    def _finalize_fallback_recipient_status(
        recipient_message: NotificationRecipientMessage,
        routing: dict[str, Any] | None,
    ) -> None:
        mode, _ = NotificationCenterService._route_steps(channels=[], routing=routing)
        if mode != "fallback":
            return
        deliveries = list(
            ChannelDelivery.objects.filter(message__recipient_message=recipient_message).order_by("route_order", "id")
        )
        if not deliveries:
            return
        if NotificationCenterService._recipient_route_succeeded(recipient_message, routing):
            return
        if any(
            row.status
            in {
                ChannelDelivery.Status.SUBMIT_UNKNOWN,
                ChannelDelivery.Status.PROCESSING,
                ChannelDelivery.Status.QUEUED,
                ChannelDelivery.Status.CREATED,
            }
            for row in deliveries
        ):
            return
        NotificationRecipientMessage.objects.filter(id=recipient_message.id).update(
            status=NotificationRecipientMessage.Status.FAILED,
            completed_at=timezone.now(),
            updated_at=timezone.now(),
        )

    @staticmethod
    def _delivery_meets_threshold(delivery: ChannelDelivery | None, threshold: str) -> bool:
        if delivery is None:
            return False
        threshold = (threshold or "provider_accepted").strip()
        if threshold == "provider_delivered":
            return delivery.status == ChannelDelivery.Status.DELIVERED
        if threshold == "client_opened":
            return delivery.provider_events.filter(normalized_type="opened").exists()
        return delivery.status in {ChannelDelivery.Status.ACCEPTED, ChannelDelivery.Status.DELIVERED}

    @staticmethod
    def _refresh_recipient_message_status(recipient_message: NotificationRecipientMessage | None) -> None:
        if recipient_message is None:
            return
        deliveries = list(
            ChannelDelivery.objects.filter(message__recipient_message=recipient_message).order_by("route_order", "id")
        )
        if not deliveries:
            status = NotificationRecipientMessage.Status.CREATED
        elif any(row.status in {ChannelDelivery.Status.CREATED, ChannelDelivery.Status.QUEUED, ChannelDelivery.Status.PROCESSING, ChannelDelivery.Status.SUBMIT_UNKNOWN} for row in deliveries):
            status = NotificationRecipientMessage.Status.PROCESSING
        else:
            routing = recipient_message.routing or {}
            mode, _ = NotificationCenterService._route_steps(channels=[], routing=routing)
            if mode == "fallback" and NotificationCenterService._recipient_route_succeeded(recipient_message, routing):
                if all(row.status == ChannelDelivery.Status.DELIVERED for row in deliveries if NotificationCenterService._delivery_meets_threshold(row, row.success_threshold)):
                    status = NotificationRecipientMessage.Status.DELIVERED
                else:
                    status = NotificationRecipientMessage.Status.ACCEPTED
            elif any(row.required and row.status in {ChannelDelivery.Status.SUBMIT_FAILED, ChannelDelivery.Status.DELIVERY_FAILED} for row in deliveries):
                status = NotificationRecipientMessage.Status.FAILED
            elif all(row.status == ChannelDelivery.Status.DELIVERED for row in deliveries):
                status = NotificationRecipientMessage.Status.DELIVERED
            elif any(row.status in {ChannelDelivery.Status.SUBMIT_FAILED, ChannelDelivery.Status.DELIVERY_FAILED} for row in deliveries):
                status = NotificationRecipientMessage.Status.PARTIAL
            elif any(row.status in {ChannelDelivery.Status.ACCEPTED, ChannelDelivery.Status.DELIVERED} for row in deliveries):
                status = NotificationRecipientMessage.Status.ACCEPTED
            else:
                status = NotificationRecipientMessage.Status.SKIPPED
        completed_at = timezone.now() if status in {
            NotificationRecipientMessage.Status.DELIVERED,
            NotificationRecipientMessage.Status.PARTIAL,
            NotificationRecipientMessage.Status.FAILED,
            NotificationRecipientMessage.Status.SKIPPED,
        } else None
        NotificationRecipientMessage.objects.filter(id=recipient_message.id).update(
            status=status,
            completed_at=completed_at,
            updated_at=timezone.now(),
        )

    @staticmethod
    def _recipient_route_succeeded(recipient_message: NotificationRecipientMessage, routing: dict[str, Any] | None) -> bool:
        mode, _ = NotificationCenterService._route_steps(channels=[], routing=routing)
        deliveries = list(
            ChannelDelivery.objects.filter(message__recipient_message=recipient_message).order_by("route_order", "id")
        )
        if not deliveries:
            return False
        results = [
            NotificationCenterService._delivery_meets_threshold(row, row.success_threshold)
            for row in deliveries
        ]
        if mode == "fallback":
            return any(results)
        required_results = [result for row, result in zip(deliveries, results) if row.required]
        return all(required_results) if required_results else any(results)

    @staticmethod
    def _mark_outbox_processed(*, campaign_id: int, last_error: str = "") -> None:
        NotificationOutbox.objects.filter(
            aggregate_type="notification_campaign",
            aggregate_id=str(campaign_id),
            event_type="notification.campaign.dispatch",
            status=NotificationOutbox.Status.PROCESSING,
        ).update(
            status=NotificationOutbox.Status.PROCESSED if not last_error else NotificationOutbox.Status.FAILED,
            last_error=last_error[:2000],
            updated_at=timezone.now(),
        )

    @staticmethod
    def _ensure_endpoint(*, user: User | None, channel: str, address: str, metadata: dict[str, Any] | None = None) -> ContactEndpoint:
        address = (address or "").strip()
        if channel == ContactEndpoint.Channel.SMS:
            hmac_value = NotificationCenterService._phone_hmac(address)
            masked = _mask_phone(address)
        elif channel == ContactEndpoint.Channel.EMAIL:
            hmac_value = NotificationCenterService._email_hmac(address)
            masked = _mask_email(address)
        else:
            hmac_value = keyed_hmac(address, scope=f"channel:{channel}")
            masked = address[:6] + "..." if len(address) > 12 else "***"

        endpoint, _ = ContactEndpoint.objects.update_or_create(
            channel=channel,
            address_hmac=hmac_value,
            defaults={
                "user": user,
                "address_ciphertext": encrypt_sensitive(address),
                "address_masked": masked,
                "is_verified": bool(metadata.get("is_verified")) if metadata else False,
                "is_active": True,
                "metadata": metadata or {},
                "request_id": (metadata or {}).get("request_id", "") if metadata else "",
            },
        )
        return endpoint

    @staticmethod
    def _record_message_event(
        *,
        message: NotificationMessage,
        channel: str,
        provider: str,
        result: _SendResult,
        endpoint: ContactEndpoint | None = None,
        details: list[dict[str, Any]] | None = None,
        route_order: int = 1,
        required: bool = True,
        success_threshold: str = "provider_accepted",
        existing_delivery: ChannelDelivery | None = None,
    ) -> NotificationMessage:
        now = result.occurred_at or timezone.now()
        status, delivery_status = NotificationCenterService._resolve_delivery_state(result)
        message.status = status
        message.provider_message_id = result.provider_message_id or message.provider_message_id
        message.provider_request_id = result.provider_request_id or message.provider_request_id
        message.provider_code = result.provider_code or message.provider_code
        message.provider_status = result.provider_status or message.provider_status
        message.error_message = "" if (result.accepted or result.delivered) else result.reason
        message.sent_at = message.sent_at or now
        if result.delivered:
            message.delivered_at = message.delivered_at or now
        if channel == NotificationMessage.Channel.SMS and endpoint and not message.receiver_phone:
            message.receiver_phone = endpoint.address_masked
        if channel == NotificationMessage.Channel.EMAIL and endpoint and not message.receiver_email:
            message.receiver_email = endpoint.address_masked
        if details is not None:
            message.delivery_details = details
        message.save()

        delivery = existing_delivery or ChannelDelivery(message=message, channel=channel)
        delivery.provider = provider
        delivery.status = delivery_status
        delivery.route_order = route_order
        delivery.required = required
        delivery.success_threshold = success_threshold
        delivery.endpoint_type = channel
        delivery.endpoint_hmac = endpoint.address_hmac if endpoint else delivery.endpoint_hmac
        delivery.endpoint_masked = endpoint.address_masked if endpoint else delivery.endpoint_masked
        delivery.provider_message_id = result.provider_message_id or ""
        delivery.provider_request_id = result.provider_request_id or ""
        delivery.provider_code = result.provider_code or ""
        delivery.provider_status = result.provider_status or ""
        delivery.accepted_at = now if (result.accepted or result.delivered) else None
        delivery.delivered_at = now if result.delivered else None
        delivery.error_code = "" if (result.accepted or result.delivered) else result.reason[:128]
        delivery.error_message = "" if (result.accepted or result.delivered) else result.reason
        delivery.details = result.provider_payload or {}
        delivery.attempt_count = max(1, delivery.attempt_count or 0)
        delivery.save()
        DeliveryAttempt.objects.update_or_create(
            delivery=delivery,
            attempt_no=delivery.attempt_count,
            defaults={
                "provider_request_id": result.provider_request_id or "",
                "provider_message_id": result.provider_message_id or "",
                "request_payload": result.provider_payload or {},
                "response_code": result.provider_code or "",
                "response_message": "" if (result.accepted or result.delivered) else result.reason,
                "outcome": (
                    DeliveryAttempt.Outcome.SUCCESS
                    if (result.accepted or result.delivered)
                    else DeliveryAttempt.Outcome.UNKNOWN
                    if result.unknown
                    else DeliveryAttempt.Outcome.FAILURE
                ),
                "error_category": "" if (result.accepted or result.delivered) else result.reason[:128],
                "duration_ms": 0,
            },
        )
        ProviderEvent.objects.create(
            delivery=delivery,
            provider=provider,
            external_event_id=f"{provider}:{result.provider_message_id or result.provider_request_id or uuid.uuid4().hex}",
            normalized_type=NotificationCenterService._provider_event_type(result),
            provider_code=result.provider_code or "",
            provider_status=result.provider_status or "",
            payload=result.provider_payload or {},
            occurred_at=now,
        )
        NotificationCenterService._refresh_recipient_message_status(message.recipient_message)
        return message

    @staticmethod
    def _sync_phone_otp_send_state(*, otp_id: str, message: NotificationMessage, delivery: ChannelDelivery | None = None) -> None:
        if not otp_id:
            return
        delivery = delivery or ChannelDelivery.objects.filter(message=message, channel=ChannelDelivery.Channel.SMS).order_by("-id").first()
        if delivery is None:
            return

        now = timezone.now()
        send_status = PhoneOTP.SendStatus.UNKNOWN
        invalidated_at = None
        send_error_code = delivery.error_code or ""
        send_error_message = delivery.error_message or message.error_message or ""
        if delivery.status in {ChannelDelivery.Status.ACCEPTED, ChannelDelivery.Status.DELIVERED}:
            send_status = PhoneOTP.SendStatus.ACCEPTED
            send_error_code = ""
            send_error_message = ""
        elif delivery.status == ChannelDelivery.Status.SUBMIT_FAILED:
            send_status = PhoneOTP.SendStatus.SUBMIT_FAILED
            invalidated_at = now
        elif delivery.status in {ChannelDelivery.Status.CANCELLED, ChannelDelivery.Status.EXPIRED}:
            send_status = PhoneOTP.SendStatus.SUBMIT_FAILED
            invalidated_at = now
            send_error_code = send_error_code or delivery.status
            send_error_message = send_error_message or delivery.status
        elif delivery.status == ChannelDelivery.Status.SUBMIT_UNKNOWN:
            send_status = PhoneOTP.SendStatus.SUBMIT_UNKNOWN
        elif delivery.status in {ChannelDelivery.Status.CREATED, ChannelDelivery.Status.QUEUED, ChannelDelivery.Status.PROCESSING}:
            send_status = PhoneOTP.SendStatus.QUEUED

        PhoneOTP.objects.filter(otp_id=otp_id).update(
            send_status=send_status,
            notification_message_id=message.id,
            provider_request_id=delivery.provider_request_id or message.provider_request_id or "",
            provider_biz_id=delivery.provider_message_id or message.provider_message_id or "",
            send_error_code=send_error_code[:128],
            send_error_message=send_error_message,
            invalidated_at=invalidated_at,
        )

    @staticmethod
    def _send_apns(
        *,
        campaign_id: int | None,
        user: User,
        title: str,
        body: str,
        payload: dict,
        created_by_id: int | None,
        request_id: str,
        topic_key: str = "",
    ) -> NotificationMessage:
        existing = NotificationCenterService._existing_message(
            campaign_id=campaign_id,
            recipient_key=str(user.id),
            channel=NotificationMessage.Channel.APNS,
            request_id=request_id,
        )
        if existing is not None:
            return existing
        active_device = DeviceSessionService.apns_trusted_device_for_user(user=user)
        devices = [active_device] if active_device else []
        details: list[dict[str, Any]] = []
        success_count = 0
        failure_count = 0
        topic = (payload.get("apns_topic") or "").strip() if isinstance(payload, dict) else ""
        provider_message_id = ""

        if not devices:
            message = NotificationMessage.objects.create(
                campaign_id=campaign_id,
                user_id=user.id,
                recipient_type=NotificationMessage.RecipientType.USER,
                recipient_key=str(user.id),
                channel=NotificationMessage.Channel.APNS,
                status=NotificationMessage.Status.SKIPPED,
                title=title or "",
                body=body or "",
                payload=payload,
                delivery_details=[],
                target_count=0,
                success_count=0,
                failure_count=0,
                apns_topic=topic,
                error_message="no_push_enabled_device",
                created_by_id=created_by_id,
                request_id=request_id or "",
                sent_at=timezone.now(),
            )
            NotificationCenterService._record_message_event(
                message=message,
                channel=NotificationMessage.Channel.APNS,
                provider="apns",
                result=_SendResult(
                    accepted=False,
                    delivered=False,
                    unknown=False,
                    skipped=True,
                    reason="no_push_enabled_device",
                    provider_message_id="",
                    provider_request_id=request_id,
                    provider_status="skipped",
                ),
                details=[],
            )
            return message

        endpoint = NotificationCenterService._ensure_endpoint(
            user=user,
            channel=ContactEndpoint.Channel.APNS,
            address=active_device.push_token if active_device else "",
            metadata={
                "bundle_id": getattr(active_device, "bundle_id", "") if active_device else "",
                "device_id": getattr(active_device, "device_id", "") if active_device else "",
                "request_id": request_id,
            },
        ) if active_device and active_device.push_token else None
        suppression_reason = NotificationCenterService._suppression_reason(
            user=user,
            channel=NotificationPreference.Channel.APNS,
            topic_key=topic_key,
            endpoint_hmac=endpoint.address_hmac if endpoint else "",
        )
        if suppression_reason:
            message = NotificationMessage.objects.create(
                campaign_id=campaign_id,
                user_id=user.id,
                recipient_type=NotificationMessage.RecipientType.USER,
                recipient_key=str(user.id),
                channel=NotificationMessage.Channel.APNS,
                status=NotificationMessage.Status.SKIPPED,
                title=title or "",
                body=body or "",
                payload=payload,
                delivery_details=[],
                target_count=0,
                success_count=0,
                failure_count=0,
                apns_topic=topic,
                error_message=suppression_reason,
                created_by_id=created_by_id,
                request_id=request_id or "",
                sent_at=timezone.now(),
            )
            return NotificationCenterService._record_message_event(
                message=message,
                channel=NotificationMessage.Channel.APNS,
                provider="apns",
                result=_SendResult(False, False, False, True, suppression_reason, "", provider_request_id=request_id, provider_status="suppressed"),
                endpoint=endpoint,
                details=[],
            )

        for dev in devices:
            ok, reason, apns_id = APNsProvider.send(
                device_token=(dev.push_token or "").strip(),
                title=title,
                body=body,
                payload=payload,
                topic=topic or (dev.bundle_identifier or dev.bundle_id or ""),
            )
            if ok:
                success_count += 1
            else:
                failure_count += 1
                if reason in APNsProvider.BAD_TOKEN_REASONS:
                    dev.push_token = ""
                    dev.notifications_enabled = False
                    dev.save(update_fields=["push_token", "notifications_enabled", "last_seen"])

            provider_message_id = provider_message_id or apns_id
            details.append(
                {
                    "device_id": dev.device_id,
                    "bundle_id": dev.bundle_id,
                    "bundle_identifier": dev.bundle_identifier,
                    "token_last4": (dev.push_token or "")[-4:],
                    "ok": ok,
                    "reason": reason,
                    "apns_id": apns_id,
                }
            )

        status_value = NotificationMessage.Status.SENT
        error_message = ""
        if failure_count == len(devices):
            status_value = NotificationMessage.Status.FAILED
            error_message = details[0].get("reason", "all_failed") if details else "all_failed"
        elif failure_count > 0:
            status_value = NotificationMessage.Status.PARTIAL

        message = NotificationMessage.objects.create(
            campaign_id=campaign_id,
            user_id=user.id,
            recipient_type=NotificationMessage.RecipientType.USER,
            recipient_key=str(user.id),
            channel=NotificationMessage.Channel.APNS,
            status=status_value,
            title=title or "",
            body=body or "",
            payload=payload,
            delivery_details=details,
            target_count=len(devices),
            success_count=success_count,
            failure_count=failure_count,
            apns_topic=topic,
            provider_message_id=provider_message_id,
            provider_request_id=request_id or "",
            error_message=error_message,
            created_by_id=created_by_id,
            request_id=request_id or "",
            sent_at=timezone.now(),
        )
        NotificationCenterService._record_message_event(
            message=message,
            channel=NotificationMessage.Channel.APNS,
            provider="apns",
            result=_SendResult(
                accepted=status_value in {NotificationMessage.Status.SENT, NotificationMessage.Status.PARTIAL},
                delivered=False,
                unknown=False,
                skipped=False,
                reason=error_message or "",
                provider_message_id=provider_message_id,
                provider_request_id=request_id,
                provider_code="OK" if status_value in {NotificationMessage.Status.SENT, NotificationMessage.Status.PARTIAL} else "APNS_ERROR",
                provider_status="accepted" if status_value in {NotificationMessage.Status.SENT, NotificationMessage.Status.PARTIAL} else "failed",
                provider_payload={"devices": details},
            ),
            endpoint=endpoint,
            details=details,
        )
        return message

    @staticmethod
    def _send_email(
        *,
        campaign_id: int | None,
        user: User,
        title: str,
        body: str,
        payload: dict,
        created_by_id: int | None,
        request_id: str,
        topic_key: str = "",
    ) -> NotificationMessage:
        existing = NotificationCenterService._existing_message(
            campaign_id=campaign_id,
            recipient_key=str(user.id),
            channel=NotificationMessage.Channel.EMAIL,
            request_id=request_id,
        )
        if existing is not None:
            return existing
        to = (user.email or "").strip()
        if not to:
            message = NotificationMessage.objects.create(
                campaign_id=campaign_id,
                user_id=user.id,
                recipient_type=NotificationMessage.RecipientType.USER,
                recipient_key=str(user.id),
                channel=NotificationMessage.Channel.EMAIL,
                status=NotificationMessage.Status.SKIPPED,
                title=title or "",
                body=body or "",
                payload=payload,
                target_count=0,
                success_count=0,
                failure_count=0,
                error_message="email_not_bound",
                created_by_id=created_by_id,
                request_id=request_id or "",
                sent_at=timezone.now(),
            )
            NotificationCenterService._record_message_event(
                message=message,
                channel=NotificationMessage.Channel.EMAIL,
                provider="email",
                result=_SendResult(False, False, False, True, "email_not_bound", "", provider_request_id=request_id, provider_status="skipped"),
                details=[],
            )
            return message

        endpoint = NotificationCenterService._ensure_endpoint(user=user, channel=ContactEndpoint.Channel.EMAIL, address=to, metadata={"request_id": request_id})
        suppression_reason = NotificationCenterService._suppression_reason(
            user=user,
            channel=NotificationPreference.Channel.EMAIL,
            topic_key=topic_key,
            endpoint_hmac=endpoint.address_hmac,
        )
        if suppression_reason:
            message = NotificationMessage.objects.create(
                campaign_id=campaign_id,
                user_id=user.id,
                recipient_type=NotificationMessage.RecipientType.USER,
                recipient_key=str(user.id),
                channel=NotificationMessage.Channel.EMAIL,
                status=NotificationMessage.Status.SKIPPED,
                title=title or "",
                body=body or "",
                payload=payload,
                target_count=0,
                success_count=0,
                failure_count=0,
                receiver_email=endpoint.address_masked,
                error_message=suppression_reason,
                created_by_id=created_by_id,
                request_id=request_id or "",
                sent_at=timezone.now(),
            )
            return NotificationCenterService._record_message_event(
                message=message,
                channel=NotificationMessage.Channel.EMAIL,
                provider="email",
                result=_SendResult(False, False, False, True, suppression_reason, "", provider_request_id=request_id, provider_status="suppressed"),
                endpoint=endpoint,
                details=[],
            )

        ok, reason, provider_message_id, smtp_detail = EmailProvider.send_notification(
            email=to, title=title, body=body, request_id=request_id
        )
        err_msg = ""
        if not ok:
            detail = (smtp_detail or "").strip()
            base = reason or "email_send_failed"
            err_msg = f"{base}: {detail}".strip(": ").strip() if detail else base
            err_msg = err_msg[:2000]

        message = NotificationMessage.objects.create(
            campaign_id=campaign_id,
            user_id=user.id,
            recipient_type=NotificationMessage.RecipientType.USER,
            recipient_key=str(user.id),
            channel=NotificationMessage.Channel.EMAIL,
            status=NotificationMessage.Status.SENT if ok else NotificationMessage.Status.FAILED,
            title=title or "",
            body=body or "",
            payload=payload,
            target_count=1,
            success_count=1 if ok else 0,
            failure_count=0 if ok else 1,
            receiver_email=endpoint.address_masked,
            provider_message_id=provider_message_id,
            provider_request_id=request_id or "",
            error_message="" if ok else err_msg,
            created_by_id=created_by_id,
            request_id=request_id or "",
            sent_at=timezone.now(),
        )
        NotificationCenterService._record_message_event(
            message=message,
            channel=NotificationMessage.Channel.EMAIL,
            provider="email",
            result=_SendResult(
                accepted=ok,
                delivered=False,
                unknown=False,
                skipped=False,
                reason="" if ok else err_msg,
                provider_message_id=provider_message_id,
                provider_request_id=request_id,
                provider_code="OK" if ok else "EMAIL_ERROR",
                provider_status="accepted" if ok else "failed",
                provider_payload={"smtp_detail": smtp_detail},
            ),
            endpoint=endpoint,
            details=[],
        )
        return message

    @staticmethod
    def _send_sms(
        *,
        campaign_id: int | None,
        user: User,
        title: str,
        body: str,
        payload: dict,
        created_by_id: int | None,
        request_id: str,
        topic_key: str = "",
    ) -> NotificationMessage:
        existing = NotificationCenterService._existing_message(
            campaign_id=campaign_id,
            recipient_key=str(user.id),
            channel=NotificationMessage.Channel.SMS,
            request_id=request_id,
        )
        if existing is not None:
            return existing
        to = NotificationCenterService._phone_number_for_user(user)
        if not to:
            message = NotificationMessage.objects.create(
                campaign_id=campaign_id,
                user_id=user.id,
                recipient_type=NotificationMessage.RecipientType.USER,
                recipient_key=str(user.id),
                channel=NotificationMessage.Channel.SMS,
                status=NotificationMessage.Status.SKIPPED,
                title=title or "",
                body=body or "",
                payload=payload,
                target_count=0,
                success_count=0,
                failure_count=0,
                error_message="phone_not_bound",
                created_by_id=created_by_id,
                request_id=request_id or "",
                sent_at=timezone.now(),
            )
            NotificationCenterService._record_message_event(
                message=message,
                channel=NotificationMessage.Channel.SMS,
                provider="aliyun",
                result=_SendResult(False, False, False, True, "phone_not_bound", "", provider_request_id=request_id, provider_status="skipped"),
                details=[],
            )
            return message

        endpoint = NotificationCenterService._ensure_endpoint(user=user, channel=ContactEndpoint.Channel.SMS, address=to, metadata={"request_id": request_id})
        suppression_reason = NotificationCenterService._suppression_reason(
            user=user,
            channel=NotificationPreference.Channel.SMS,
            topic_key=topic_key,
            endpoint_hmac=endpoint.address_hmac,
        )
        if suppression_reason:
            message = NotificationMessage.objects.create(
                campaign_id=campaign_id,
                user_id=user.id,
                recipient_type=NotificationMessage.RecipientType.USER,
                recipient_key=str(user.id),
                channel=NotificationMessage.Channel.SMS,
                status=NotificationMessage.Status.SKIPPED,
                title=title or "",
                body=body or "",
                payload=payload,
                target_count=0,
                success_count=0,
                failure_count=0,
                receiver_phone=endpoint.address_masked,
                error_message=suppression_reason,
                created_by_id=created_by_id,
                request_id=request_id or "",
                sent_at=timezone.now(),
            )
            return NotificationCenterService._record_message_event(
                message=message,
                channel=NotificationMessage.Channel.SMS,
                provider="aliyun",
                result=_SendResult(False, False, False, True, suppression_reason, "", provider_request_id=request_id, provider_status="suppressed"),
                endpoint=endpoint,
                details=[],
            )

        sms_result = AliyunSMSProvider.send(phone_number=to, title=title, body=body)
        message = NotificationMessage.objects.create(
            campaign_id=campaign_id,
            user_id=user.id,
            recipient_type=NotificationMessage.RecipientType.USER,
            recipient_key=str(user.id),
            channel=NotificationMessage.Channel.SMS,
            status=NotificationMessage.Status.SENT if sms_result.accepted else NotificationMessage.Status.FAILED,
            title=title or "",
            body=body or "",
            payload=payload,
            target_count=1,
            success_count=1 if sms_result.accepted else 0,
            failure_count=0 if (sms_result.accepted or sms_result.unknown) else 1,
            receiver_phone=endpoint.address_masked,
            provider_message_id=sms_result.biz_id,
            provider_request_id=sms_result.request_id or request_id or "",
            error_message="" if sms_result.accepted else sms_result.reason,
            created_by_id=created_by_id,
            request_id=request_id or "",
            sent_at=timezone.now(),
        )
        NotificationCenterService._record_message_event(
            message=message,
            channel=NotificationMessage.Channel.SMS,
            provider="aliyun",
            result=_SendResult(
                accepted=sms_result.accepted,
                delivered=False,
                unknown=sms_result.unknown,
                skipped=False,
                reason="" if sms_result.accepted else sms_result.reason,
                provider_message_id=sms_result.biz_id,
                provider_request_id=sms_result.request_id or request_id,
                provider_code=sms_result.code or ("OK" if sms_result.accepted else "SMS_ERROR"),
                provider_status=sms_result.status or ("accepted" if sms_result.accepted else "failed"),
                provider_payload=sms_result.payload or {},
            ),
            endpoint=endpoint,
            details=[],
        )
        return message

    @staticmethod
    def create_campaign_and_enqueue(
        *,
        channels: list[str],
        title: str,
        body: str,
        payload: dict | None,
        user_id: int | None,
        user_ids: list[int] | None,
        filters: dict | None,
        template_id: int | None,
        schedule_at,
        campaign_name: str,
        created_by_id: int | None,
        request_id: str,
    ) -> NotificationCampaign:
        if request_id:
            existing = NotificationCampaign.objects.filter(request_id=request_id).order_by("-id").first()
            if existing is not None:
                return existing
        target_user_ids = NotificationCenterService.resolve_target_user_ids(user_id=user_id, user_ids=user_ids, filters=filters)
        if not target_user_ids:
            raise ValueError("no_target_users")

        template = NotificationTemplate.objects.filter(id=template_id).first() if template_id else None
        now = timezone.now()
        schedule_time = schedule_at if schedule_at and schedule_at > now else None
        idempotency_key = request_id or f"campaign:{uuid.uuid4().hex}"
        scene_key = "operation.campaign.published"
        topic_key = (template.topic_key if template else "marketing.campaign") or "marketing.campaign"
        template_version = template.versions.filter(status=NotificationTemplateVersion.Status.PUBLISHED).order_by("-version").first() if template else None
        routing = ((payload or {}).get("_routing") if isinstance(payload, dict) else None) or {"mode": "parallel", "steps": [{"channel": channel, "required": True} for channel in list(dict.fromkeys(channels))]}
        scene = NotificationCenterService.ensure_business_scene(scene_key, topic_key=topic_key)
        event_id = request_id or uuid.uuid4().hex

        with transaction.atomic():
            intent, _ = NotificationIntent.objects.get_or_create(
                idempotency_key=idempotency_key,
                defaults={
                    "topic_key": topic_key,
                    "business_scene": scene.key,
                    "business_domain": scene.domain,
                    "business_type": scene.business_type,
                    "business_reference_type": "notification_campaign",
                    "business_id": "",
                    "subject_type": "",
                    "subject_id": "",
                    "template_key": template.key if template else "",
                    "template_version": template_version,
                    "routing": routing,
                    "scene_contract_version": scene.contract_version,
                    "scene_snapshot": NotificationCenterService._scene_snapshot(scene),
                    "event_id": event_id,
                    "occurred_at": now,
                    "actor_type": "user" if created_by_id else "",
                    "actor_id": str(created_by_id or ""),
                    "trace_id": request_id or "",
                    "source": "backoffice",
                    "status": NotificationIntent.Status.CREATED,
                    "priority": 100,
                    "scheduled_at": schedule_time,
                },
            )
            existing_campaign = NotificationCampaign.objects.filter(intent=intent).order_by("-id").first()
            if existing_campaign is not None:
                return existing_campaign
            campaign = NotificationCampaign.objects.create(
                name=(campaign_name or "").strip(),
                status=NotificationCampaign.Status.SCHEDULED if schedule_time else NotificationCampaign.Status.QUEUED,
                channels=list(dict.fromkeys(channels)),
                title=title or "",
                body=body or "",
                payload=payload or {},
                filters=filters or {},
                target_user_ids=[],
                target_count=len(target_user_ids),
                template=template,
                intent=intent,
                created_by_id=created_by_id,
                request_id=request_id or "",
                scheduled_at=schedule_time,
            )
            AudienceDefinition.objects.create(
                campaign=campaign,
                source_type="filters" if filters else "explicit",
                criteria=filters or {"user_ids": target_user_ids},
                version=1,
            )
            AudienceSnapshot.objects.bulk_create(
                [
                    AudienceSnapshot(
                        campaign=campaign,
                        user_id=target_user_id,
                        recipient_type="user",
                        recipient_key=str(target_user_id),
                        status=AudienceSnapshot.Status.INCLUDED,
                        position=position,
                    )
                    for position, target_user_id in enumerate(target_user_ids, start=1)
                ],
                batch_size=1000,
            )
            NotificationOutbox.objects.create(
                aggregate_type="notification_campaign",
                aggregate_id=str(campaign.id),
                event_type="notification.campaign.dispatch",
                payload={"campaign_id": campaign.id, "request_id": request_id or "", "routing": routing},
                idempotency_key=idempotency_key,
                status=NotificationOutbox.Status.PENDING,
                available_at=schedule_time or now,
            )
            from notification_center.tasks import relay_notification_outbox_task

            transaction.on_commit(lambda: relay_notification_outbox_task.delay())

        return campaign

    @staticmethod
    def execute_campaign(*, campaign_id: int, request_id: str = "", task_id: str = "") -> dict[str, Any]:
        with transaction.atomic():
            campaign = NotificationCampaign.objects.select_for_update().filter(id=campaign_id).first()
            if campaign is None:
                raise ValueError("campaign_not_found")
            if campaign.status in {NotificationCampaign.Status.COMPLETED, NotificationCampaign.Status.FAILED, NotificationCampaign.Status.CANCELLED}:
                return {
                    "campaign_id": campaign.id,
                    "status": campaign.status,
                    "target_count": campaign.target_count,
                    "success_count": campaign.success_count,
                    "failure_count": campaign.failure_count,
                    "task_id": campaign.task_id,
                    "request_id": campaign.request_id,
                }
            campaign.status = NotificationCampaign.Status.RUNNING
            campaign.started_at = timezone.now()
            if task_id:
                campaign.task_id = task_id
            campaign.save(update_fields=["status", "started_at", "task_id", "updated_at"])
            if campaign.intent_id:
                NotificationIntent.objects.filter(id=campaign.intent_id).update(status=NotificationIntent.Status.DISPATCHED, updated_at=timezone.now())
        snapshot_user_ids = list(
            campaign.audience_snapshots.filter(status=AudienceSnapshot.Status.INCLUDED, user_id__isnull=False)
            .order_by("position", "id")
            .values_list("user_id", flat=True)
        )
        if not snapshot_user_ids and campaign.target_user_ids:
            snapshot_user_ids = list(campaign.target_user_ids)
        users = list(User.objects.filter(id__in=snapshot_user_ids).order_by("id"))
        channel_stats = defaultdict(lambda: {"target": 0, "success": 0, "failure": 0})
        success_total = 0
        failure_total = 0
        recipient_success_total = 0
        recipient_failure_total = 0

        dispatch_request_id = request_id or campaign.request_id or f"campaign:{campaign.id}"
        for user in users:
            title_rendered, body_rendered, payload_rendered = NotificationCenterService.build_message_content(
                user=user,
                template=campaign.template,
                template_version=campaign.intent.template_version if campaign.intent_id else None,
                title=campaign.title,
                body=campaign.body,
                payload=campaign.payload,
            )
            logs = NotificationCenterService.send_to_user_sync(
                campaign_id=campaign.id,
                user_id=user.id,
                channels=campaign.channels,
                title=title_rendered,
                body=body_rendered,
                payload=payload_rendered,
                created_by_id=campaign.created_by_id,
                request_id=dispatch_request_id,
                topic_key=(campaign.intent.topic_key if campaign.intent_id else "") or (campaign.template.topic_key if campaign.template_id else ""),
                routing=(campaign.intent.routing if campaign.intent_id else None),
            )
            for log in logs:
                channel_stats[log.channel]["target"] += int(log.target_count or 0)
                channel_stats[log.channel]["success"] += int(log.success_count or 0)
                channel_stats[log.channel]["failure"] += int(log.failure_count or 0)
                success_total += int(log.success_count or 0)
                failure_total += int(log.failure_count or 0)

            recipient_message = logs[0].recipient_message if logs else None
            if recipient_message and NotificationCenterService._recipient_route_succeeded(
                recipient_message,
                campaign.intent.routing if campaign.intent_id else None,
            ):
                recipient_success_total += 1
            else:
                recipient_failure_total += 1

        final_status = NotificationCampaign.Status.COMPLETED if recipient_success_total > 0 else NotificationCampaign.Status.FAILED
        NotificationCampaign.objects.filter(id=campaign.id).update(
            status=final_status,
            success_count=success_total,
            failure_count=failure_total,
            finished_at=timezone.now(),
            error_message="" if final_status == NotificationCampaign.Status.COMPLETED else "all_channels_failed",
            updated_at=timezone.now(),
        )
        if campaign.intent_id:
            NotificationIntent.objects.filter(id=campaign.intent_id).update(
                status=NotificationIntent.Status.COMPLETED if final_status == NotificationCampaign.Status.COMPLETED else NotificationIntent.Status.FAILED,
                updated_at=timezone.now(),
            )
        NotificationCenterService._mark_outbox_processed(campaign_id=campaign.id)
        if final_status == NotificationCampaign.Status.FAILED:
            NotificationCenterService._mark_outbox_processed(campaign_id=campaign.id, last_error="all_channels_failed")

        return {
            "campaign_id": campaign.id,
            "status": final_status,
            "target_count": campaign.target_count,
            "success_count": success_total,
            "failure_count": failure_total,
            "recipient_success_count": recipient_success_total,
            "recipient_failure_count": recipient_failure_total,
            "channel_stats": channel_stats,
            "task_id": campaign.task_id,
            "request_id": campaign.request_id,
        }

    @staticmethod
    def send_to_user_sync(
        *,
        campaign_id: int | None,
        user_id: int,
        channels: list[str],
        title: str,
        body: str,
        payload: dict | None,
        created_by_id: int | None,
        request_id: str = "",
        topic_key: str = "",
        routing: dict[str, Any] | None = None,
        business_scene: str = "",
        business_reference_type: str = "",
        business_id: str = "",
        idempotency_key: str = "",
        source: str = "legacy_adapter",
        actor_type: str = "",
        actor_id: str = "",
    ) -> list[NotificationMessage]:
        user = User.objects.filter(id=user_id).first()
        if user is None:
            raise ValueError("user_not_found")

        normalized_scene = NotificationCenterService._normalize_scene_key(business_scene)
        if normalized_scene in MEMBERSHIP_USER_NOTIFICATION_SUPPRESSED_SCENES:
            logger.info(
                "notification.membership.route.suppressed scene=%s user_id=%s reason=scene_disabled",
                normalized_scene,
                user_id,
            )
            return []

        payload = payload or {}
        out: list[NotificationMessage] = []
        campaign = NotificationCampaign.objects.filter(id=campaign_id).select_related("intent").first() if campaign_id else None
        intent = campaign.intent if campaign else None
        scene = None
        if intent is None:
            if not business_scene:
                raise ValueError("business_scene_required")
            scene = NotificationCenterService.ensure_business_scene(business_scene, topic_key=topic_key)
            topic_key = topic_key or (scene.topic.key if scene.topic else "") or scene.default_template_key or scene.key
            routing = routing or payload.get("_routing") or scene.default_routing
            now = timezone.now()
            intent_idempotency_key = (
                idempotency_key
                or request_id
                or f"{scene.key}:user:{user.id}:{business_reference_type or 'none'}:{business_id or uuid.uuid4().hex}"
            )
            event_id = uuid.uuid4().hex
            intent, _ = NotificationIntent.objects.get_or_create(
                idempotency_key=intent_idempotency_key,
                defaults={
                    "topic_key": topic_key,
                    "business_scene": scene.key,
                    "business_domain": scene.domain,
                    "business_type": scene.business_type,
                    "business_reference_type": business_reference_type or "",
                    "business_id": str(business_id or ""),
                    "subject_type": "user",
                    "subject_id": str(user.id),
                    "routing": routing or {},
                    "scene_contract_version": scene.contract_version,
                    "scene_snapshot": NotificationCenterService._scene_snapshot(scene),
                    "event_id": event_id,
                    "occurred_at": now,
                    "actor_type": actor_type or ("user" if created_by_id else ""),
                    "actor_id": actor_id or str(created_by_id or ""),
                    "trace_id": request_id or "",
                    "source": source or "legacy_adapter",
                    "status": NotificationIntent.Status.CREATED,
                    "priority": 100,
                },
            )
        else:
            topic_key = topic_key or intent.topic_key
            routing = routing or payload.get("_routing") or intent.routing

        mode, steps, _resolved_channels = NotificationCenterService._resolve_send_routing(
            channels=channels,
            routing=routing or payload.get("_routing"),
            business_scene=business_scene or (intent.business_scene if intent else ""),
        )
        membership_scene_key = business_scene or (intent.business_scene if intent else "")
        if mode == "fallback" and membership_scene_key.startswith("membership."):
            logger.info(
                "notification.membership.route.start scene=%s user_id=%s routing_mode=%s steps=%s business_id=%s",
                membership_scene_key,
                user_id,
                mode,
                ",".join(step["channel"] for step in steps),
                business_id or "-",
            )
        recipient_message, _ = NotificationRecipientMessage.objects.get_or_create(
            campaign_id=campaign_id,
            intent_id=intent.id if intent else None,
            recipient_type=NotificationMessage.RecipientType.USER,
            recipient_key=str(user.id),
            defaults={
                "user": user,
                "routing": routing or payload.get("_routing") or {},
                "request_id": request_id,
            },
        )
        for step in sorted(steps, key=lambda item: (item.get("route_order", 0), item.get("channel", ""))):
            channel = step["channel"]
            if channel == NotificationMessage.Channel.APNS:
                message = NotificationCenterService._send_apns(campaign_id=campaign_id, user=user, title=title, body=body, payload=payload, created_by_id=created_by_id, request_id=request_id, topic_key=topic_key)
            elif channel == NotificationMessage.Channel.EMAIL:
                message = NotificationCenterService._send_email(campaign_id=campaign_id, user=user, title=title, body=body, payload=payload, created_by_id=created_by_id, request_id=request_id, topic_key=topic_key)
            elif channel == NotificationMessage.Channel.SMS:
                message = NotificationCenterService._send_sms(campaign_id=campaign_id, user=user, title=title, body=body, payload=payload, created_by_id=created_by_id, request_id=request_id, topic_key=topic_key)
            else:
                continue
            if message.recipient_message_id != recipient_message.id:
                message.recipient_message = recipient_message
            if message.intent_id != (intent.id if intent else None):
                message.intent = intent
            message.save(update_fields=["recipient_message", "intent", "updated_at"])
            ChannelDelivery.objects.filter(message=message).update(
                route_order=step.get("route_order", 1),
                required=step.get("required", True),
                success_threshold=step.get("success_threshold", "provider_accepted"),
            )
            NotificationCenterService._refresh_recipient_message_status(recipient_message)
            out.append(message)
            delivery = ChannelDelivery.objects.filter(message=message).order_by("-id").first()
            if membership_scene_key.startswith("membership."):
                logger.info(
                    "notification.membership.route.step scene=%s user_id=%s channel=%s route_order=%s status=%s stop=%s",
                    membership_scene_key,
                    user_id,
                    channel,
                    step.get("route_order", 1),
                    delivery.status if delivery else "-",
                    not NotificationCenterService._should_continue_fallback(mode=mode, delivery=delivery, step=step),
                )
            if not NotificationCenterService._should_continue_fallback(mode=mode, delivery=delivery, step=step):
                break
            if mode != "fallback" and step.get("required", True) and message.status == NotificationMessage.Status.FAILED:
                break
        NotificationCenterService._finalize_fallback_recipient_status(recipient_message, routing)
        if mode == "fallback" and membership_scene_key.startswith("membership."):
            recipient_message.refresh_from_db()
            winning = (
                ChannelDelivery.objects.filter(
                    message__recipient_message=recipient_message,
                    status__in={ChannelDelivery.Status.ACCEPTED, ChannelDelivery.Status.DELIVERED},
                )
                .order_by("route_order", "id")
                .values_list("channel", flat=True)
                .first()
            )
            logger.info(
                "notification.membership.route.done scene=%s user_id=%s final_status=%s winning_channel=%s",
                membership_scene_key,
                user_id,
                recipient_message.status,
                winning or "-",
            )
        return out

    @staticmethod
    def send_phone_otp(
        *,
        phone_number: str,
        code: str,
        request_id: str = "",
        provider_uid: str = "",
        user_id: int | None = None,
        scene: str = "login",
        bundle_id: str = "",
        device_id: str = "",
        ip_address: str = "",
        otp_id: str = "",
        expires_at=None,
        dispatch_sync: bool = True,
    ) -> tuple[bool, str, str]:
        normalized_phone = NotificationCenterService._normalize_phone(phone_number)
        if not normalized_phone:
            return False, "phone_number_missing", ""
        readiness_error = AliyunSMSProvider.otp_readiness_error()
        if readiness_error:
            return False, readiness_error, ""

        phone_ref = keyed_hmac(normalized_phone, scope="otp-rate-phone")
        ip_ref = keyed_hmac(ip_address or "unknown", scope="otp-rate-ip")
        for key, limit in ((f"nc:otp:phone:{phone_ref}", 5), (f"nc:otp:ip:{ip_ref}", 20), (f"nc:otp:pair:{phone_ref}:{ip_ref}", 10)):
            try:
                cache.add(key, 0, timeout=3600)
                if cache.incr(key) > limit:
                    return False, "otp_rate_limited", ""
            except Exception:  # noqa: BLE001
                logger.warning("notification_center otp rate limiter unavailable request_id=%s", request_id or "-")
                return False, "otp_rate_limit_unavailable", ""

        now = timezone.now()
        expiry = expires_at or now + timedelta(minutes=5)
        scene_key = NotificationCenterService._normalize_scene_key(scene)
        if scene_key not in _BUILTIN_BUSINESS_SCENES and scene_key not in {
            "account.auth.login_otp_requested",
            "account.auth.registration_otp_requested",
            "account.lifecycle.deactivation_requested",
        }:
            scene_key = _BUSINESS_SCENE_ALIASES.get(scene_key, scene_key or "account.auth.login_otp_requested")
        scene_row = NotificationCenterService.ensure_business_scene(scene_key)
        idempotency_key = f"{scene_row.key}:{otp_id or request_id or uuid.uuid4().hex}"
        event_id = otp_id or request_id or uuid.uuid4().hex
        with transaction.atomic():
            intent, created = NotificationIntent.objects.get_or_create(
                idempotency_key=idempotency_key,
                defaults={
                    "topic_key": "security.authentication",
                    "business_scene": scene_row.key,
                    "business_domain": scene_row.domain,
                    "business_type": scene_row.business_type,
                    "business_reference_type": "phone_otp",
                    "business_id": otp_id or "",
                    "subject_type": "user" if user_id else "contact",
                    "subject_id": str(user_id or normalized_phone),
                    "routing": {"mode": "parallel", "steps": [{"channel": "sms", "required": True, "success_threshold": "provider_accepted"}]},
                    "scene_contract_version": scene_row.contract_version,
                    "scene_snapshot": NotificationCenterService._scene_snapshot(scene_row),
                    "event_id": event_id,
                    "occurred_at": now,
                    "actor_type": "user" if user_id else "",
                    "actor_id": str(user_id or ""),
                    "trace_id": request_id or "",
                    "source": "accounts.otp",
                    "status": NotificationIntent.Status.CREATED,
                    "priority": 1,
                    "expires_at": expiry,
                    "sensitive_context_ciphertext": encrypt_sensitive(json.dumps({"phone_number": normalized_phone, "code": code, "scene": scene_row.key})),
                },
            )
            existing = NotificationMessage.objects.filter(intent=intent, channel=NotificationMessage.Channel.SMS).first()
            if existing is not None:
                if not dispatch_sync or existing.status in {NotificationMessage.Status.ACCEPTED, NotificationMessage.Status.DELIVERED, NotificationMessage.Status.FAILED, NotificationMessage.Status.SKIPPED}:
                    return existing.status in {NotificationMessage.Status.ACCEPTED, NotificationMessage.Status.DELIVERED}, existing.error_message, str(existing.id)
                message = existing
            else:
                user = User.objects.filter(id=user_id).first() if user_id else None
                endpoint = NotificationCenterService._ensure_endpoint(
                    user=user,
                    channel=ContactEndpoint.Channel.SMS,
                    address=normalized_phone,
                    metadata={
                        "provider_uid": provider_uid,
                        "bundle_id": bundle_id,
                        "device_id": device_id,
                        "ip_address": ip_address,
                        "request_id": request_id,
                    },
                )
                message = NotificationMessage.objects.create(
                    intent=intent,
                    user=user,
                    recipient_type=NotificationMessage.RecipientType.USER if user else NotificationMessage.RecipientType.CONTACT,
                    recipient_key=endpoint.address_hmac,
                    channel=NotificationMessage.Channel.SMS,
                    status=NotificationMessage.Status.QUEUED,
                    title="验证码短信",
                    body="",
                    payload={
                        "scene": scene_row.key,
                        "business_scene": scene_row.key,
                        "business_type": scene_row.business_type,
                        "business_id": otp_id or "",
                    },
                    target_count=1,
                    receiver_phone=endpoint.address_masked,
                    request_id=request_id or "",
                )
                NotificationOutbox.objects.create(
                    aggregate_type="notification_intent",
                    aggregate_id=str(intent.id),
                    event_type="notification.sms_otp.dispatch",
                    payload={"intent_id": intent.id, "message_id": message.id},
                    idempotency_key=idempotency_key,
                    status=NotificationOutbox.Status.PROCESSING if dispatch_sync else NotificationOutbox.Status.PENDING,
                    available_at=now,
                )
                if not dispatch_sync:
                    from notification_center.tasks import relay_notification_outbox_task

                    transaction.on_commit(lambda: relay_notification_outbox_task.delay())
        if not dispatch_sync:
            return True, "", str(message.id)

        result = NotificationCenterService.execute_phone_otp_intent(intent_id=intent.id, message_id=message.id)
        status = result.get("status", "")
        if status in {ChannelDelivery.Status.ACCEPTED, ChannelDelivery.Status.DELIVERED}:
            return True, "", str(message.id)
        reason = result.get("reason") or result.get("error_message") or status or "sms_send_failed"
        return False, str(reason), str(message.id)

    @staticmethod
    def send_email_otp(
        *,
        email: str,
        code: str,
        request_id: str = "",
        provider_uid: str = "",
        scene: str = "login",
        bundle_id: str = "",
        device_id: str = "",
        ip_address: str = "",
        otp_id: str = "",
        expires_at=None,
    ) -> tuple[bool, str, str]:
        address = (email or "").strip().lower()
        if not address:
            return False, "email_missing", ""

        now = timezone.now()
        expiry = expires_at or now + timedelta(minutes=5)
        email_context = NotificationCenterService._email_otp_context(
            email=address,
            code=code,
            expires_at=expiry,
            request_id=request_id or "",
        )
        scene_key = NotificationCenterService._normalize_scene_key(scene)
        if scene_key not in {
            "account.auth.login_otp_requested",
            "account.auth.registration_otp_requested",
            "account.auth.identity_bind_otp_requested",
            "account.auth.identity_change_otp_requested",
            "account.auth.identity_reauth_otp_requested",
            "account.auth.password_reset_otp_requested",
        }:
            scene_key = _BUSINESS_SCENE_ALIASES.get(scene_key, scene_key or "account.auth.login_otp_requested")
        scene_row = NotificationCenterService.ensure_business_scene(scene_key)
        idempotency_key = f"{scene_row.key}:email:{otp_id or request_id or uuid.uuid4().hex}"
        event_id = otp_id or uuid.uuid4().hex
        with transaction.atomic():
            intent, _ = NotificationIntent.objects.get_or_create(
                idempotency_key=idempotency_key,
                defaults={
                    "topic_key": "security.authentication",
                    "business_scene": scene_row.key,
                    "business_domain": scene_row.domain,
                    "business_type": scene_row.business_type,
                    "business_reference_type": "email_otp",
                    "business_id": otp_id or "",
                    "subject_type": "contact",
                    "subject_id": keyed_hmac(address, scope="email-otp-subject"),
                    "routing": {"mode": "parallel", "steps": [{"channel": "email", "required": True, "success_threshold": "provider_accepted"}]},
                    "scene_contract_version": scene_row.contract_version,
                    "scene_snapshot": NotificationCenterService._scene_snapshot(scene_row),
                    "event_id": event_id,
                    "occurred_at": now,
                    "trace_id": request_id or "",
                    "source": "accounts.otp",
                    "status": NotificationIntent.Status.CREATED,
                    "priority": 1,
                    "expires_at": expiry,
                    "sensitive_context_ciphertext": encrypt_sensitive(json.dumps({"email": address, "code": code, "scene": scene_row.key})),
                },
            )
            existing = NotificationMessage.objects.filter(intent=intent, channel=NotificationMessage.Channel.EMAIL).first()
            if existing is not None:
                return existing.status not in {NotificationMessage.Status.FAILED, NotificationMessage.Status.SKIPPED}, existing.error_message, str(existing.id)
            endpoint = NotificationCenterService._ensure_endpoint(
                user=None,
                channel=ContactEndpoint.Channel.EMAIL,
                address=address,
                metadata={
                    "provider_uid": provider_uid,
                    "bundle_id": bundle_id,
                    "device_id": device_id,
                    "ip_address": ip_address,
                    "request_id": request_id,
                },
            )
            message = NotificationMessage.objects.create(
                intent=intent,
                user=None,
                recipient_type=NotificationMessage.RecipientType.CONTACT,
                recipient_key=endpoint.address_hmac,
                channel=NotificationMessage.Channel.EMAIL,
                status=NotificationMessage.Status.QUEUED,
                title="验证码邮件",
                body="",
                payload={
                    "scene": scene_row.key,
                    "business_scene": scene_row.key,
                    "business_type": scene_row.business_type,
                    "business_id": otp_id or "",
                },
                target_count=1,
                receiver_email=endpoint.address_masked,
                request_id=request_id or "",
            )
            NotificationOutbox.objects.create(
                aggregate_type="notification_intent",
                aggregate_id=str(intent.id),
                event_type="notification.email_otp.dispatch",
                payload={"intent_id": intent.id, "message_id": message.id},
                idempotency_key=idempotency_key,
                status=NotificationOutbox.Status.PENDING,
                available_at=now,
            )
            from notification_center.tasks import relay_notification_outbox_task

            transaction.on_commit(lambda: relay_notification_outbox_task.delay())
        return True, "", str(message.id)

    @staticmethod
    def execute_email_otp_intent(*, intent_id: int, message_id: int, task_id: str = "") -> dict[str, Any]:
        with transaction.atomic():
            intent = NotificationIntent.objects.select_for_update().get(id=intent_id)
            message = NotificationMessage.objects.select_for_update().get(id=message_id, intent=intent)
            existing_delivery = ChannelDelivery.objects.filter(message=message).order_by("-id").first()
            if existing_delivery and existing_delivery.status in {ChannelDelivery.Status.ACCEPTED, ChannelDelivery.Status.DELIVERED, ChannelDelivery.Status.SUBMIT_UNKNOWN}:
                return {"status": existing_delivery.status, "message_id": message.id}
            if intent.expires_at and intent.expires_at <= timezone.now():
                intent.status = NotificationIntent.Status.EXPIRED
                intent.sensitive_context_ciphertext = ""
                intent.save(update_fields=["status", "sensitive_context_ciphertext", "updated_at"])
                message.status = NotificationMessage.Status.SKIPPED
                message.error_message = "otp_expired"
                message.save(update_fields=["status", "error_message", "updated_at"])
                NotificationOutbox.objects.filter(aggregate_type="notification_intent", aggregate_id=str(intent.id)).update(status=NotificationOutbox.Status.PROCESSED, updated_at=timezone.now())
                return {"status": "expired", "message_id": message.id}
            if not intent.sensitive_context_ciphertext:
                raise ValueError("otp_sensitive_context_missing")
            context = json.loads(decrypt_sensitive(intent.sensitive_context_ciphertext))
            email_context = NotificationCenterService._email_otp_context(
                email=context["email"],
                code=context["code"],
                expires_at=intent.expires_at,
                request_id=message.request_id,
            )
            endpoint = ContactEndpoint.objects.get(channel=ContactEndpoint.Channel.EMAIL, address_hmac=message.recipient_key)
            delivery, delivery_created = ChannelDelivery.objects.get_or_create(
                message=message,
                channel=ChannelDelivery.Channel.EMAIL,
                defaults={
                    "provider": "smtp",
                    "status": ChannelDelivery.Status.PROCESSING,
                    "endpoint_type": ContactEndpoint.Channel.EMAIL,
                    "endpoint_hmac": endpoint.address_hmac,
                    "endpoint_masked": endpoint.address_masked,
                    "success_threshold": "provider_accepted",
                    "attempt_count": 1,
                },
            )
            if not delivery_created and delivery.status == ChannelDelivery.Status.PROCESSING:
                delivery.status = ChannelDelivery.Status.SUBMIT_UNKNOWN
                delivery.error_code = "worker_interrupted_after_provider_call"
                delivery.save(update_fields=["status", "error_code", "updated_at"])
                intent.status = NotificationIntent.Status.COMPLETED
                intent.sensitive_context_ciphertext = ""
                intent.save(update_fields=["status", "sensitive_context_ciphertext", "updated_at"])
                NotificationOutbox.objects.filter(aggregate_type="notification_intent", aggregate_id=str(intent.id)).update(status=NotificationOutbox.Status.PROCESSED, updated_at=timezone.now())
                return {"status": ChannelDelivery.Status.SUBMIT_UNKNOWN, "message_id": message.id}
            intent.status = NotificationIntent.Status.DISPATCHED
            intent.save(update_fields=["status", "updated_at"])
            message.status = NotificationMessage.Status.PROCESSING
            message.save(update_fields=["status", "updated_at"])

        ok, reason, provider_message_id, detail = EmailProvider.send_notification(
            email=email_context["email"],
            title=email_context["subject"],
            body=NotificationCenterService._render_email_otp_text(email_context),
            html_body=NotificationCenterService._render_email_otp_html(email_context),
            request_id=message.request_id,
        )
        provider_payload = {"otp": True}
        if detail:
            provider_payload["detail"] = detail
        NotificationCenterService._record_message_event(
            message=message,
            channel=NotificationMessage.Channel.EMAIL,
            provider="email",
            result=_SendResult(
                accepted=ok,
                delivered=False,
                unknown=False,
                skipped=False,
                reason="" if ok else reason,
                provider_message_id=provider_message_id,
                provider_request_id=message.request_id,
                provider_code="OK" if ok else "EMAIL_ERROR",
                provider_status="accepted" if ok else "failed",
                provider_payload=provider_payload,
            ),
            endpoint=endpoint,
            details=[],
            existing_delivery=delivery,
        )
        NotificationIntent.objects.filter(id=intent.id).update(
            status=NotificationIntent.Status.COMPLETED if ok else NotificationIntent.Status.FAILED,
            sensitive_context_ciphertext="",
            updated_at=timezone.now(),
        )
        NotificationOutbox.objects.filter(aggregate_type="notification_intent", aggregate_id=str(intent.id)).update(
            status=NotificationOutbox.Status.PROCESSED,
            last_error="" if ok else reason[:2000],
            updated_at=timezone.now(),
        )
        return {"status": delivery.status, "message_id": message.id, "provider_message_id": provider_message_id}

    @staticmethod
    def execute_phone_otp_intent(*, intent_id: int, message_id: int, task_id: str = "") -> dict[str, Any]:
        with transaction.atomic():
            intent = NotificationIntent.objects.select_for_update().get(id=intent_id)
            message = NotificationMessage.objects.select_for_update().get(id=message_id, intent=intent)
            existing_delivery = ChannelDelivery.objects.filter(message=message).order_by("-id").first()
            if existing_delivery and existing_delivery.status in {ChannelDelivery.Status.ACCEPTED, ChannelDelivery.Status.DELIVERED, ChannelDelivery.Status.SUBMIT_UNKNOWN}:
                NotificationCenterService._sync_phone_otp_send_state(otp_id=intent.business_id, message=message, delivery=existing_delivery)
                return {
                    "status": existing_delivery.status,
                    "message_id": message.id,
                    "reason": existing_delivery.error_message or existing_delivery.error_code,
                }
            if intent.expires_at and intent.expires_at <= timezone.now():
                intent.status = NotificationIntent.Status.EXPIRED
                intent.sensitive_context_ciphertext = ""
                intent.save(update_fields=["status", "sensitive_context_ciphertext", "updated_at"])
                message.status = NotificationMessage.Status.SKIPPED
                message.error_message = "otp_expired"
                message.save(update_fields=["status", "error_message", "updated_at"])
                NotificationOutbox.objects.filter(aggregate_type="notification_intent", aggregate_id=str(intent.id)).update(status=NotificationOutbox.Status.PROCESSED, updated_at=timezone.now())
                if existing_delivery:
                    existing_delivery.status = ChannelDelivery.Status.EXPIRED
                    existing_delivery.error_code = "otp_expired"
                    existing_delivery.error_message = "otp_expired"
                    existing_delivery.save(update_fields=["status", "error_code", "error_message", "updated_at"])
                    NotificationCenterService._sync_phone_otp_send_state(otp_id=intent.business_id, message=message, delivery=existing_delivery)
                else:
                    PhoneOTP.objects.filter(otp_id=intent.business_id).update(
                        send_status=PhoneOTP.SendStatus.SUBMIT_FAILED,
                        notification_message_id=message.id,
                        send_error_code="otp_expired",
                        send_error_message="otp_expired",
                        invalidated_at=timezone.now(),
                    )
                return {"status": "expired", "message_id": message.id}
            if not intent.sensitive_context_ciphertext:
                raise ValueError("otp_sensitive_context_missing")
            context = json.loads(decrypt_sensitive(intent.sensitive_context_ciphertext))
            endpoint = ContactEndpoint.objects.get(channel=ContactEndpoint.Channel.SMS, address_hmac=message.recipient_key)
            delivery, delivery_created = ChannelDelivery.objects.get_or_create(
                message=message,
                channel=ChannelDelivery.Channel.SMS,
                defaults={
                    "provider": "aliyun",
                    "status": ChannelDelivery.Status.PROCESSING,
                    "endpoint_type": ContactEndpoint.Channel.SMS,
                    "endpoint_hmac": endpoint.address_hmac,
                    "endpoint_masked": endpoint.address_masked,
                    "success_threshold": "provider_accepted",
                    "attempt_count": 1,
                },
            )
            if not delivery_created and delivery.status == ChannelDelivery.Status.PROCESSING:
                delivery.status = ChannelDelivery.Status.SUBMIT_UNKNOWN
                delivery.error_code = "worker_interrupted_after_provider_call"
                delivery.save(update_fields=["status", "error_code", "updated_at"])
                intent.status = NotificationIntent.Status.COMPLETED
                intent.sensitive_context_ciphertext = ""
                intent.save(update_fields=["status", "sensitive_context_ciphertext", "updated_at"])
                NotificationOutbox.objects.filter(aggregate_type="notification_intent", aggregate_id=str(intent.id)).update(status=NotificationOutbox.Status.PROCESSED, updated_at=timezone.now())
                NotificationCenterService._sync_phone_otp_send_state(otp_id=intent.business_id, message=message, delivery=delivery)
                return {"status": ChannelDelivery.Status.SUBMIT_UNKNOWN, "message_id": message.id, "reason": delivery.error_code}
            intent.status = NotificationIntent.Status.DISPATCHED
            intent.save(update_fields=["status", "updated_at"])
            message.status = NotificationMessage.Status.PROCESSING
            message.save(update_fields=["status", "updated_at"])

        sms_result = AliyunSMSProvider.send_login_code(phone_number=context["phone_number"], code=context["code"])
        NotificationCenterService._record_message_event(
            message=message,
            channel=NotificationMessage.Channel.SMS,
            provider="aliyun",
            result=_SendResult(
                accepted=sms_result.accepted,
                delivered=False,
                unknown=sms_result.unknown,
                skipped=False,
                reason="" if sms_result.accepted else sms_result.reason,
                provider_message_id=sms_result.biz_id,
                provider_request_id=sms_result.request_id,
                provider_code=sms_result.code or ("OK" if sms_result.accepted else "SMS_ERROR"),
                provider_status=sms_result.status or ("accepted" if sms_result.accepted else "failed"),
                provider_payload={
                    "otp": True,
                    **(sms_result.payload or {}),
                    "template_param": {
                        **(((sms_result.payload or {}).get("template_param") or {}) if isinstance((sms_result.payload or {}).get("template_param"), dict) else {}),
                        "code": context.get("code") or "",
                    },
                },
            ),
            endpoint=endpoint,
            details=[],
            existing_delivery=delivery,
        )
        delivery.refresh_from_db()
        message.refresh_from_db()
        receipt_result = None
        if sms_result.accepted and delivery.provider_message_id:
            receipt_result = NotificationCenterService._wait_for_sms_delivery_receipt(
                message=message,
                delivery=delivery,
                phone_number=context["phone_number"],
                request_id=message.request_id or "",
                max_attempts=3,
                interval_seconds=1,
            )
            delivery.refresh_from_db()
            message.refresh_from_db()
        NotificationCenterService._sync_phone_otp_send_state(otp_id=intent.business_id, message=message, delivery=delivery)
        receipt_failed = bool(receipt_result is not None and receipt_result.get("status") == ChannelDelivery.Status.DELIVERY_FAILED)
        final_success = bool(sms_result.accepted and not receipt_failed)
        final_error = ""
        if not final_success:
            final_error = (
                (receipt_result or {}).get("reason")
                or sms_result.reason
                or "sms_send_failed"
            )
        NotificationIntent.objects.filter(id=intent.id).update(
            status=NotificationIntent.Status.COMPLETED if final_success else NotificationIntent.Status.FAILED,
            sensitive_context_ciphertext="",
            updated_at=timezone.now(),
        )
        NotificationOutbox.objects.filter(aggregate_type="notification_intent", aggregate_id=str(intent.id)).update(
            status=NotificationOutbox.Status.PROCESSED,
            last_error="" if final_success else str(final_error or "")[:2000],
            updated_at=timezone.now(),
        )
        if receipt_result is not None and receipt_result.get("status") == ChannelDelivery.Status.DELIVERED:
            return {"status": ChannelDelivery.Status.DELIVERED, "message_id": message.id, "biz_id": sms_result.biz_id, "reason": ""}
        if receipt_result is not None and receipt_result.get("status") == ChannelDelivery.Status.DELIVERY_FAILED:
            return {
                "status": ChannelDelivery.Status.DELIVERY_FAILED,
                "message_id": message.id,
                "biz_id": sms_result.biz_id,
                "reason": receipt_result.get("reason") or "sms_delivery_failed",
            }
        if sms_result.accepted:
            return {"status": ChannelDelivery.Status.ACCEPTED, "message_id": message.id, "biz_id": sms_result.biz_id, "reason": ""}
        return {"status": delivery.status, "message_id": message.id, "biz_id": sms_result.biz_id, "reason": sms_result.reason}

    @staticmethod
    def _wait_for_sms_delivery_receipt(
        *,
        message: NotificationMessage,
        delivery: ChannelDelivery,
        phone_number: str,
        request_id: str = "",
        max_attempts: int = 10,
        interval_seconds: int = 1,
    ) -> dict[str, Any]:
        attempts = max(1, int(max_attempts or 1))
        interval = max(0, int(interval_seconds or 0))
        query_phone = NotificationCenterService._sms_receipt_query_phone(phone_number)
        for attempt in range(1, attempts + 1):
            if interval:
                time_module.sleep(interval)
            query_send_date = NotificationCenterService._sms_receipt_query_send_date(delivery)
            query_result = AliyunSMSProvider.query_send_details(
                phone_number=query_phone,
                biz_id=delivery.provider_message_id,
                send_date=query_send_date,
                current_page=1,
                page_size=10,
                request_id=request_id or "",
            )
            now = timezone.now()
            details = {**(delivery.details or {}), **(query_result.payload or {})}
            if query_result.normalized_status == "delivered":
                delivery.status = ChannelDelivery.Status.DELIVERED
                delivery.delivered_at = query_result.delivered_at or now
                delivery.error_code = ""
                delivery.error_message = ""
                delivery.provider_status = query_result.provider_status or delivery.provider_status
                delivery.provider_code = query_result.code or delivery.provider_code
                delivery.provider_request_id = query_result.request_id or delivery.provider_request_id
                delivery.details = details
                delivery.save(update_fields=["status", "delivered_at", "error_code", "error_message", "provider_status", "provider_code", "provider_request_id", "details", "updated_at"])
                NotificationMessage.objects.filter(id=message.id).update(
                    status=NotificationMessage.Status.DELIVERED,
                    delivered_at=delivery.delivered_at,
                    error_message="",
                    provider_status=query_result.provider_status or "delivered",
                    provider_code=query_result.code or "",
                    provider_request_id=query_result.request_id or message.provider_request_id,
                    updated_at=now,
                )
                return {"status": ChannelDelivery.Status.DELIVERED, "attempt": attempt, "reason": ""}
            if query_result.normalized_status == "delivery_failed":
                delivery.status = ChannelDelivery.Status.DELIVERY_FAILED
                delivery.error_code = query_result.code or "carrier_delivery_failed"
                delivery.error_message = query_result.reason or query_result.code or "carrier_delivery_failed"
                delivery.provider_status = query_result.provider_status or delivery.provider_status
                delivery.provider_code = query_result.code or delivery.provider_code
                delivery.provider_request_id = query_result.request_id or delivery.provider_request_id
                delivery.details = details
                delivery.save(update_fields=["status", "error_code", "error_message", "provider_status", "provider_code", "provider_request_id", "details", "updated_at"])
                NotificationMessage.objects.filter(id=message.id).update(
                    status=NotificationMessage.Status.FAILED,
                    error_message=delivery.error_message,
                    provider_status=query_result.provider_status or "delivery_failed",
                    provider_code=query_result.code or "",
                    provider_request_id=query_result.request_id or message.provider_request_id,
                    updated_at=now,
                )
                return {"status": ChannelDelivery.Status.DELIVERY_FAILED, "attempt": attempt, "reason": delivery.error_message}
            delivery.provider_status = query_result.provider_status or delivery.provider_status
            delivery.provider_code = query_result.code or delivery.provider_code
            delivery.provider_request_id = query_result.request_id or delivery.provider_request_id
            delivery.details = details
            delivery.save(update_fields=["provider_status", "provider_code", "provider_request_id", "details", "updated_at"])

        delivery.status = ChannelDelivery.Status.ACCEPTED
        delivery.error_code = ""
        delivery.error_message = ""
        delivery.save(update_fields=["status", "error_code", "error_message", "updated_at"])
        NotificationMessage.objects.filter(id=message.id).update(
            status=NotificationMessage.Status.ACCEPTED,
            error_message="",
            updated_at=timezone.now(),
        )
        return {"status": ChannelDelivery.Status.ACCEPTED, "attempt": attempts, "reason": ""}

    @staticmethod
    def poll_pending_sms_deliveries(*, limit: int = 100) -> dict[str, int]:
        deliveries = list(
            ChannelDelivery.objects.select_related("message")
            .filter(channel=ChannelDelivery.Channel.SMS, status__in=[ChannelDelivery.Status.ACCEPTED, ChannelDelivery.Status.SUBMIT_UNKNOWN])
            .order_by("updated_at", "id")[: max(1, min(limit, 500))]
        )
        delivered = 0
        failed = 0
        unknown = 0
        for delivery in deliveries:
            try:
                phone_number = ""
                if delivery.endpoint_hmac:
                    endpoint = ContactEndpoint.objects.filter(channel=ContactEndpoint.Channel.SMS, address_hmac=delivery.endpoint_hmac).first()
                    if endpoint is not None:
                        phone_number = decrypt_sensitive(endpoint.address_ciphertext)
                if not phone_number:
                    unknown += 1
                    continue
                query_send_date = NotificationCenterService._sms_receipt_query_send_date(delivery)
                query_result = AliyunSMSProvider.query_send_details(
                    phone_number=NotificationCenterService._sms_receipt_query_phone(phone_number),
                    biz_id=delivery.provider_message_id,
                    send_date=query_send_date,
                )
                if query_result.normalized_status == "delivered":
                    delivery.status = ChannelDelivery.Status.DELIVERED
                    delivery.delivered_at = query_result.delivered_at or timezone.now()
                    delivery.error_code = ""
                    delivery.error_message = ""
                    delivered += 1
                    if delivery.message_id:
                        NotificationMessage.objects.filter(id=delivery.message_id).update(
                            delivered_at=delivery.delivered_at,
                            provider_status=query_result.provider_status or "delivered",
                            provider_code=query_result.code or "",
                            updated_at=timezone.now(),
                        )
                elif query_result.normalized_status == "delivery_failed":
                    delivery.status = ChannelDelivery.Status.DELIVERY_FAILED
                    delivery.error_code = query_result.code or "carrier_delivery_failed"
                    delivery.error_message = query_result.reason or query_result.code or "carrier_delivery_failed"
                    failed += 1
                    if delivery.message_id:
                        NotificationMessage.objects.filter(id=delivery.message_id).update(
                            status=NotificationMessage.Status.FAILED,
                            error_message=delivery.error_message,
                            provider_status=query_result.provider_status or "delivery_failed",
                            provider_code=query_result.code or "",
                            updated_at=timezone.now(),
                        )
                else:
                    unknown += 1
                    delivery.status = ChannelDelivery.Status.SUBMIT_UNKNOWN if query_result.normalized_status == "unknown" else ChannelDelivery.Status.ACCEPTED
                delivery.provider_status = query_result.provider_status or delivery.provider_status
                delivery.provider_code = query_result.code or delivery.provider_code
                if query_result.payload:
                    delivery.details = {**(delivery.details or {}), **query_result.payload}
                delivery.save(update_fields=["status", "delivered_at", "error_code", "error_message", "provider_status", "provider_code", "details", "updated_at"])
            except Exception:  # noqa: BLE001
                logger.exception("notification_center poll_pending_sms_deliveries failed delivery_id=%s", delivery.id)
                unknown += 1
        return {"total": len(deliveries), "delivered": delivered, "failed": failed, "unknown": unknown}

    @staticmethod
    def query_sms_send_details_for_message(*, message_id: int, request_id: str = "", operator_user_id: int | None = None) -> NotificationMessage:
        message = NotificationMessage.objects.get(id=message_id, channel=NotificationMessage.Channel.SMS)
        delivery = (
            ChannelDelivery.objects.select_related("message")
            .filter(message_id=message.id, channel=ChannelDelivery.Channel.SMS)
            .order_by("-created_at", "-id")
            .first()
        )
        if delivery is None:
            logger.warning(
                "notification.sms.query_send_details.failed",
                extra={"action": "notification.sms.query_send_details", "request_id": request_id or "", "message_id": message_id, "operator_user_id": operator_user_id, "reason": "sms_delivery_not_found"},
            )
            raise ValueError("sms_delivery_not_found")
        if not delivery.provider_message_id:
            logger.warning(
                "notification.sms.query_send_details.failed",
                extra={"action": "notification.sms.query_send_details", "request_id": request_id or "", "message_id": message_id, "delivery_id": delivery.id, "operator_user_id": operator_user_id, "reason": "sms_biz_id_missing"},
            )
            raise ValueError("sms_biz_id_missing")
        if not delivery.endpoint_hmac:
            logger.warning(
                "notification.sms.query_send_details.failed",
                extra={"action": "notification.sms.query_send_details", "request_id": request_id or "", "message_id": message_id, "delivery_id": delivery.id, "operator_user_id": operator_user_id, "reason": "sms_endpoint_missing"},
            )
            raise ValueError("sms_endpoint_missing")

        endpoint = ContactEndpoint.objects.filter(channel=ContactEndpoint.Channel.SMS, address_hmac=delivery.endpoint_hmac).first()
        if endpoint is None:
            logger.warning(
                "notification.sms.query_send_details.failed",
                extra={"action": "notification.sms.query_send_details", "request_id": request_id or "", "message_id": message_id, "delivery_id": delivery.id, "operator_user_id": operator_user_id, "reason": "sms_endpoint_missing"},
            )
            raise ValueError("sms_endpoint_missing")
        phone_number = decrypt_sensitive(endpoint.address_ciphertext)
        if not phone_number:
            logger.warning(
                "notification.sms.query_send_details.failed",
                extra={"action": "notification.sms.query_send_details", "request_id": request_id or "", "message_id": message_id, "delivery_id": delivery.id, "operator_user_id": operator_user_id, "reason": "sms_phone_missing"},
            )
            raise ValueError("sms_phone_missing")

        query_phone = NotificationCenterService._sms_receipt_query_phone(phone_number)
        query_send_date = NotificationCenterService._sms_receipt_query_send_date(delivery)
        logger.info(
            "notification.sms.query_send_details.begin message_id=%s delivery_id=%s biz_id=%s phone_number=%s send_date=%s operator_user_id=%s",
            message.id,
            delivery.id,
            delivery.provider_message_id,
            query_phone,
            query_send_date.strftime("%Y%m%d"),
            operator_user_id or "-",
            extra={
                "action": "notification.sms.query_send_details",
                "request_id": request_id or "",
                "message_id": message.id,
                "delivery_id": delivery.id,
                "operator_user_id": operator_user_id,
                "biz_id": delivery.provider_message_id,
                "phone_number": query_phone,
                "send_date": query_send_date.strftime("%Y%m%d"),
                "send_date_source": "message.sent_at" if message.sent_at else "delivery.accepted_at" if delivery.accepted_at else "delivery.created_at",
            },
        )
        query_result = AliyunSMSProvider.query_send_details(
            phone_number=query_phone,
            biz_id=delivery.provider_message_id,
            send_date=query_send_date,
            current_page=1,
            page_size=10,
            request_id=request_id or "",
        )
        now = timezone.now()
        if query_result.normalized_status == "delivered":
            delivery.status = ChannelDelivery.Status.DELIVERED
            delivery.delivered_at = query_result.delivered_at or now
            delivery.error_code = ""
            delivery.error_message = ""
            message.status = NotificationMessage.Status.DELIVERED
            message.delivered_at = delivery.delivered_at
            message.error_message = ""
        elif query_result.normalized_status == "delivery_failed":
            delivery.status = ChannelDelivery.Status.DELIVERY_FAILED
            delivery.error_code = query_result.code or "carrier_delivery_failed"
            delivery.error_message = query_result.reason or query_result.code or "carrier_delivery_failed"
            message.status = NotificationMessage.Status.FAILED
            message.error_message = delivery.error_message
        else:
            delivery.status = ChannelDelivery.Status.SUBMIT_UNKNOWN if query_result.normalized_status == "unknown" else ChannelDelivery.Status.ACCEPTED

        delivery.provider_status = query_result.provider_status or delivery.provider_status
        delivery.provider_code = query_result.code or delivery.provider_code
        delivery.provider_request_id = query_result.request_id or delivery.provider_request_id
        if query_result.payload:
            delivery.details = {**(delivery.details or {}), **query_result.payload}
        delivery.save(update_fields=["status", "delivered_at", "error_code", "error_message", "provider_status", "provider_code", "provider_request_id", "details", "updated_at"])

        message.provider_status = query_result.provider_status or message.provider_status
        message.provider_code = query_result.code or message.provider_code
        message.provider_request_id = query_result.request_id or message.provider_request_id
        message.save(update_fields=["status", "delivered_at", "error_message", "provider_status", "provider_code", "provider_request_id", "updated_at"])
        logger.info(
            "notification.sms.query_send_details.result message_id=%s delivery_id=%s biz_id=%s normalized_status=%s provider_request_id=%s provider_code=%s provider_status=%s reason=%s",
            message.id,
            delivery.id,
            delivery.provider_message_id,
            query_result.normalized_status,
            query_result.request_id or "-",
            query_result.code or "-",
            query_result.provider_status or "-",
            query_result.reason or "-",
            extra={
                "action": "notification.sms.query_send_details",
                "request_id": request_id or "",
                "message_id": message.id,
                "delivery_id": delivery.id,
                "operator_user_id": operator_user_id,
                "biz_id": delivery.provider_message_id,
                "provider_request_id": query_result.request_id or "",
                "provider_code": query_result.code or "",
                "provider_status": query_result.provider_status or "",
                "normalized_status": query_result.normalized_status,
                "reason": query_result.reason or "",
            },
        )
        return message

    @staticmethod
    def requeue_stuck_outbox(*, stale_seconds: int = 300) -> int:
        threshold = timezone.now() - timedelta(seconds=max(60, stale_seconds))
        rows = NotificationOutbox.objects.filter(status=NotificationOutbox.Status.PROCESSING, updated_at__lt=threshold)
        count = 0
        for row in rows:
            campaign = NotificationCampaign.objects.filter(id=row.aggregate_id).first() if row.aggregate_type == "notification_campaign" else None
            if campaign and campaign.status == NotificationCampaign.Status.COMPLETED:
                continue
            if campaign and campaign.status == NotificationCampaign.Status.RUNNING:
                campaign.status = NotificationCampaign.Status.QUEUED
                campaign.error_message = "requeued_after_stale_worker"
                campaign.save(update_fields=["status", "error_message", "updated_at"])
            row.status = NotificationOutbox.Status.PENDING
            row.last_error = "requeued_after_stale_processing"
            row.save(update_fields=["status", "last_error", "updated_at"])
            count += 1
        return count

    @staticmethod
    def send_contact_email(
        *,
        email: str,
        title: str,
        body: str,
        request_id: str = "",
        business_scene: str = "",
        business_reference_type: str = "",
        business_id: str = "",
        idempotency_key: str = "",
        source: str = "contact_adapter",
    ) -> tuple[bool, str, str, str]:
        address = (email or "").strip().lower()
        if not address:
            return False, "email_missing", "", ""
        endpoint = NotificationCenterService._ensure_endpoint(user=None, channel=ContactEndpoint.Channel.EMAIL, address=address, metadata={"request_id": request_id})
        existing = NotificationCenterService._existing_message(
            campaign_id=None,
            recipient_key=endpoint.address_hmac,
            channel=NotificationMessage.Channel.EMAIL,
            request_id=request_id,
        )
        if existing is not None:
            return existing.status in {NotificationMessage.Status.ACCEPTED, NotificationMessage.Status.DELIVERED, NotificationMessage.Status.SENT}, existing.error_message, existing.provider_message_id, ""

        intent = None
        if business_scene:
            scene = NotificationCenterService.ensure_business_scene(business_scene)
            intent, _ = NotificationIntent.objects.get_or_create(
                idempotency_key=idempotency_key or request_id or f"{scene.key}:contact_email:{endpoint.address_hmac}:{business_id or uuid.uuid4().hex}",
                defaults={
                    "topic_key": scene.topic.key if scene.topic else scene.key,
                    "business_scene": scene.key,
                    "business_domain": scene.domain,
                    "business_type": scene.business_type,
                    "business_reference_type": business_reference_type or "",
                    "business_id": str(business_id or ""),
                    "subject_type": "contact",
                    "subject_id": endpoint.address_hmac,
                    "routing": {"mode": "parallel", "steps": [{"channel": "email", "required": True}]},
                    "scene_contract_version": scene.contract_version,
                    "scene_snapshot": NotificationCenterService._scene_snapshot(scene),
                    "event_id": uuid.uuid4().hex,
                    "occurred_at": timezone.now(),
                    "trace_id": request_id or "",
                    "source": source or "contact_adapter",
                    "status": NotificationIntent.Status.DISPATCHED,
                },
            )
        ok, reason, provider_message_id, detail = EmailProvider.send_notification(
            email=address,
            title=title,
            body=body,
            request_id=request_id,
        )
        message = NotificationMessage.objects.create(
            campaign_id=None,
            intent=intent,
            user=None,
            recipient_type=NotificationMessage.RecipientType.CONTACT,
            recipient_key=endpoint.address_hmac,
            channel=NotificationMessage.Channel.EMAIL,
            status=NotificationMessage.Status.SENT if ok else NotificationMessage.Status.FAILED,
            title=title or "",
            body=body or "",
            payload={},
            target_count=1,
            success_count=1 if ok else 0,
            failure_count=0 if ok else 1,
            receiver_email=endpoint.address_masked,
            provider_message_id=provider_message_id,
            provider_request_id=request_id or "",
            provider_code="OK" if ok else "EMAIL_ERROR",
            provider_status="accepted" if ok else "failed",
            error_message="" if ok else reason,
            request_id=request_id or "",
            sent_at=timezone.now(),
        )
        if intent is not None:
            NotificationIntent.objects.filter(id=intent.id).update(
                status=NotificationIntent.Status.COMPLETED if ok else NotificationIntent.Status.FAILED,
                updated_at=timezone.now(),
            )
        NotificationCenterService._record_message_event(
            message=message,
            channel=NotificationMessage.Channel.EMAIL,
            provider="email",
            result=_SendResult(
                accepted=ok,
                delivered=False,
                unknown=False,
                skipped=False,
                reason="" if ok else reason,
                provider_message_id=provider_message_id,
                provider_request_id=request_id,
                provider_code="OK" if ok else "EMAIL_ERROR",
                provider_status="accepted" if ok else "failed",
                provider_payload={"detail": detail} if detail else {},
            ),
            endpoint=endpoint,
            details=[],
        )
        return ok, reason, provider_message_id, detail

    @staticmethod
    def send_contact_sms(
        *,
        phone_number: str,
        title: str,
        body: str,
        request_id: str = "",
        business_scene: str = "",
        business_reference_type: str = "",
        business_id: str = "",
        idempotency_key: str = "",
        source: str = "contact_adapter",
    ) -> tuple[bool, str, str]:
        normalized_phone = NotificationCenterService._normalize_phone(phone_number)
        if not normalized_phone:
            return False, "phone_number_missing", ""
        endpoint = NotificationCenterService._ensure_endpoint(user=None, channel=ContactEndpoint.Channel.SMS, address=normalized_phone, metadata={"request_id": request_id})
        existing = NotificationCenterService._existing_message(
            campaign_id=None,
            recipient_key=endpoint.address_hmac,
            channel=NotificationMessage.Channel.SMS,
            request_id=request_id,
        )
        if existing is not None:
            return existing.status in {NotificationMessage.Status.ACCEPTED, NotificationMessage.Status.DELIVERED, NotificationMessage.Status.SENT}, existing.error_message, existing.provider_message_id

        intent = None
        if business_scene:
            scene = NotificationCenterService.ensure_business_scene(business_scene)
            intent, _ = NotificationIntent.objects.get_or_create(
                idempotency_key=idempotency_key or request_id or f"{scene.key}:contact_sms:{endpoint.address_hmac}:{business_id or uuid.uuid4().hex}",
                defaults={
                    "topic_key": scene.topic.key if scene.topic else scene.key,
                    "business_scene": scene.key,
                    "business_domain": scene.domain,
                    "business_type": scene.business_type,
                    "business_reference_type": business_reference_type or "",
                    "business_id": str(business_id or ""),
                    "subject_type": "contact",
                    "subject_id": endpoint.address_hmac,
                    "routing": {"mode": "parallel", "steps": [{"channel": "sms", "required": True}]},
                    "scene_contract_version": scene.contract_version,
                    "scene_snapshot": NotificationCenterService._scene_snapshot(scene),
                    "event_id": uuid.uuid4().hex,
                    "occurred_at": timezone.now(),
                    "trace_id": request_id or "",
                    "source": source or "contact_adapter",
                    "status": NotificationIntent.Status.DISPATCHED,
                },
            )
        sms_result = AliyunSMSProvider.send(phone_number=normalized_phone, title=title, body=body)
        message = NotificationMessage.objects.create(
            campaign_id=None,
            intent=intent,
            user=None,
            recipient_type=NotificationMessage.RecipientType.CONTACT,
            recipient_key=endpoint.address_hmac,
            channel=NotificationMessage.Channel.SMS,
            status=NotificationMessage.Status.SENT if sms_result.accepted else NotificationMessage.Status.FAILED,
            title=title or "",
            body=body or "",
            payload={},
            target_count=1,
            success_count=1 if sms_result.accepted else 0,
            failure_count=0 if (sms_result.accepted or sms_result.unknown) else 1,
            receiver_phone=endpoint.address_masked,
            provider_message_id=sms_result.biz_id,
            provider_request_id=sms_result.request_id or request_id or "",
            provider_code=sms_result.code or ("OK" if sms_result.accepted else "SMS_ERROR"),
            provider_status=sms_result.status or ("accepted" if sms_result.accepted else "failed"),
            error_message="" if sms_result.accepted else sms_result.reason,
            request_id=request_id or "",
            sent_at=timezone.now(),
        )
        if intent is not None:
            NotificationIntent.objects.filter(id=intent.id).update(
                status=NotificationIntent.Status.COMPLETED if sms_result.accepted else NotificationIntent.Status.FAILED,
                updated_at=timezone.now(),
            )
        NotificationCenterService._record_message_event(
            message=message,
            channel=NotificationMessage.Channel.SMS,
            provider="aliyun",
            result=_SendResult(
                accepted=sms_result.accepted,
                delivered=False,
                unknown=sms_result.unknown,
                skipped=False,
                reason="" if sms_result.accepted else sms_result.reason,
                provider_message_id=sms_result.biz_id,
                provider_request_id=sms_result.request_id or request_id,
                provider_code=sms_result.code or ("OK" if sms_result.accepted else "SMS_ERROR"),
                provider_status=sms_result.status or ("accepted" if sms_result.accepted else "failed"),
                provider_payload=sms_result.payload or {},
            ),
            endpoint=endpoint,
            details=[],
        )
        return sms_result.accepted, sms_result.reason, sms_result.biz_id
