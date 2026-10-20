"""Version-controlled notification business-scene catalog.

The database is the operational projection; this module is the source of truth for
scenes shipped by SparkService.  Product-created draft scenes may coexist in the
database, but application code must never manufacture active scenes at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from django.db import transaction

from notification_center.models import NotificationBusinessScene, NotificationTopic


MEMBERSHIP_FALLBACK_ROUTING: dict[str, Any] = {
    "mode": "fallback",
    "steps": [
        {"channel": "apns", "route_order": 1, "required": False, "success_threshold": "provider_accepted"},
        {"channel": "email", "route_order": 2, "required": False, "success_threshold": "provider_accepted"},
        {"channel": "sms", "route_order": 3, "required": False, "success_threshold": "provider_accepted"},
    ],
}

# Scenes kept in the catalog for documentation but must not create user notifications yet.
MEMBERSHIP_USER_NOTIFICATION_SUPPRESSED_SCENES: frozenset[str] = frozenset(
    {
        "membership.pro_trial.expiring",
        "membership.pro_trial.revoked",
    }
)


@dataclass(frozen=True)
class SceneDefinition:
    key: str
    display_name: str
    category: str = NotificationBusinessScene.Category.TRANSACTIONAL
    severity: str = NotificationBusinessScene.Severity.INFO
    description: str = ""
    topic_key: str = ""
    default_template_key: str = ""
    channels: tuple[str, ...] = ("in_app",)
    default_routing: dict[str, Any] | None = None
    preference_policy: str = "opt_out"
    quiet_hour_policy: str = "respect"
    contract_version: int = 1
    owner_team: str = ""
    variable_schema: dict[str, Any] = field(default_factory=dict)
    reference_schema: dict[str, Any] = field(default_factory=dict)
    client_action_schema: dict[str, Any] = field(default_factory=dict)

    @property
    def domain(self) -> str:
        return self.key.split(".", 1)[0]

    @property
    def business_type(self) -> str:
        return ".".join(self.key.split(".")[:2])

    @property
    def event_name(self) -> str:
        return self.key.rsplit(".", 1)[-1]

    def defaults(self, topic: NotificationTopic | None = None) -> dict[str, Any]:
        routing = self.default_routing or {
            "mode": "parallel",
            "steps": [{"channel": channel, "required": False} for channel in self.channels],
        }
        return {
            "key": self.key,
            "domain": self.domain,
            "business_type": self.business_type,
            "event_name": self.event_name,
            "display_name": self.display_name,
            "description": self.description,
            "topic": topic,
            "category": self.category,
            "severity": self.severity,
            "default_template_key": self.default_template_key,
            "default_routing": routing,
            "variable_schema": self.variable_schema,
            "reference_schema": self.reference_schema,
            "client_action_schema": self.client_action_schema,
            "preference_policy": self.preference_policy,
            "quiet_hour_policy": self.quiet_hour_policy,
            "status": NotificationBusinessScene.Status.ACTIVE,
            "contract_version": self.contract_version,
            "owner_team": self.owner_team,
        }


SECURITY = NotificationBusinessScene.Category.SECURITY
WARNING = NotificationBusinessScene.Severity.WARNING
CRITICAL = NotificationBusinessScene.Severity.CRITICAL
SUCCESS = NotificationBusinessScene.Severity.SUCCESS


def _scene(key: str, name: str, *, channels=("in_app",), **kwargs: Any) -> SceneDefinition:
    return SceneDefinition(key=key, display_name=name, channels=channels, **kwargs)


# Append-only catalog. Renaming a key is a breaking protocol change: deprecate the
# old definition and add a new one instead.
SCENE_CATALOG: tuple[SceneDefinition, ...] = (
    _scene("account.auth.registration_otp_requested", "注册验证码", category=SECURITY, channels=("sms", "email"), preference_policy="mandatory", quiet_hour_policy="bypass"),
    _scene("account.auth.login_otp_requested", "登录验证码", category=SECURITY, channels=("sms", "email"), preference_policy="mandatory", quiet_hour_policy="bypass"),
    _scene("account.auth.identity_bind_otp_requested", "绑定身份验证码", category=SECURITY, channels=("sms", "email"), preference_policy="mandatory", quiet_hour_policy="bypass"),
    _scene("account.auth.identity_change_otp_requested", "换绑身份验证码", category=SECURITY, channels=("sms", "email"), preference_policy="mandatory", quiet_hour_policy="bypass"),
    _scene("account.auth.identity_reauth_otp_requested", "身份再认证验证码", category=SECURITY, channels=("sms", "email"), preference_policy="mandatory", quiet_hour_policy="bypass"),
    _scene("account.auth.password_reset_otp_requested", "重置凭证验证码", category=SECURITY, channels=("sms", "email"), preference_policy="mandatory", quiet_hour_policy="bypass"),
    _scene("account.security.new_device_login_detected", "新设备登录", category=SECURITY, severity=WARNING, channels=("apns", "email"), preference_policy="mandatory"),
    _scene("account.security.suspicious_login_detected", "异常登录", category=SECURITY, severity=CRITICAL, channels=("apns", "sms", "email"), preference_policy="mandatory", quiet_hour_policy="bypass_critical"),
    _scene("account.security.credential_changed", "凭证已修改", category=SECURITY, severity=WARNING, channels=("apns", "email"), preference_policy="mandatory"),
    _scene("account.lifecycle.registration_completed", "注册完成", severity=SUCCESS, channels=("apns", "email", "in_app")),
    _scene("account.lifecycle.deactivation_requested", "注销申请已受理", severity=WARNING, channels=("apns", "email", "in_app"), preference_policy="mandatory"),
    _scene("account.lifecycle.deactivation_cancelled", "注销已撤销", channels=("apns", "email", "in_app"), preference_policy="mandatory"),
    _scene("account.lifecycle.deactivation_completed", "注销完成", severity=CRITICAL, channels=("email", "sms"), preference_policy="mandatory", quiet_hour_policy="bypass"),
    _scene("account.lifecycle.deactivation_failed", "注销处理失败", severity=WARNING, channels=("email", "in_app"), preference_policy="mandatory"),
    _scene(
        "account.lifecycle.login_banned",
        "账号违规禁登通知",
        category=SECURITY,
        severity=CRITICAL,
        channels=("sms",),
        preference_policy="mandatory",
        quiet_hour_policy="bypass",
    ),
    _scene("membership.pro_trial.application_submitted", "Pro 试用申请已提交", channels=("apns", "in_app")),
    _scene(
        "membership.pro_trial.application_approved",
        "Pro 试用申请通过",
        severity=SUCCESS,
        channels=("apns", "email", "sms"),
        default_routing=MEMBERSHIP_FALLBACK_ROUTING,
    ),
    _scene("membership.pro_trial.application_rejected", "Pro 试用申请未通过", channels=("apns", "in_app")),
    _scene(
        "membership.pro_trial.manually_granted",
        "系统发放试用",
        severity=SUCCESS,
        channels=("apns", "email", "sms"),
        default_routing=MEMBERSHIP_FALLBACK_ROUTING,
    ),
    _scene("membership.pro_trial.activated", "试用已生效", severity=SUCCESS, channels=("apns", "in_app")),
    # Catalog only — user notifications suppressed until product enables expiring reminders.
    _scene("membership.pro_trial.expiring", "试用即将到期", severity=WARNING, channels=("apns", "in_app", "email")),
    _scene("membership.pro_trial.expired", "试用已到期", channels=("apns", "in_app")),
    # Catalog only — user notifications suppressed until product enables revocation notices.
    _scene("membership.pro_trial.revoked", "试用已收回", severity=WARNING, channels=("apns", "in_app", "email")),
    _scene("system.announcement.published", "系统公告", category=NotificationBusinessScene.Category.SYSTEM, channels=("apns", "email", "in_app")),
    _scene("operation.campaign.published", "运营活动发布", category=NotificationBusinessScene.Category.OPERATIONAL, channels=("apns", "email", "in_app")),
)

SCENE_CATALOG += tuple(_scene('diary.customization.'+action, name, channels=('apns',), topic_key='diary.customization', default_template_key='diary.customization.'+action, owner_team='traveldiary') for action,name in (
    ('pending_reminder','定制人工提醒'),('info_requested','定制待补充'),('due_changed','定制日期调整'),('rejected','定制无法制作'),('cancelled','定制已取消'),
    ('delivered','定制首次交付'),('redelivered','定制修订交付'),('delivery_withdrawn','定制交付撤回'),('delivery_rolled_back','定制版本回滚')))

SCENE_BY_KEY = {definition.key: definition for definition in SCENE_CATALOG}
if len(SCENE_BY_KEY) != len(SCENE_CATALOG):  # pragma: no cover - import-time invariant
    raise RuntimeError("duplicate notification business scene key")


@transaction.atomic
def sync_business_scenes(*, definitions: Iterable[SceneDefinition] = SCENE_CATALOG) -> tuple[int, int]:
    """Idempotently project the code catalog into the database."""
    created = updated = 0
    for definition in definitions:
        topic = NotificationTopic.objects.filter(key=definition.topic_key).first() if definition.topic_key else None
        _, was_created = NotificationBusinessScene.objects.update_or_create(
            key=definition.key,
            defaults={key: value for key, value in definition.defaults(topic).items() if key != "key"},
        )
        created += int(was_created)
        updated += int(not was_created)
    return created, updated
