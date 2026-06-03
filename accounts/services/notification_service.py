import logging
from collections import defaultdict
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from accounts.infrastructure.apns_provider import APNsProvider
from accounts.infrastructure.email_provider import EmailProvider
from accounts.infrastructure.sms_provider import AliyunSMSProvider
from accounts.models import (
    AccountDeviceSession,
    NotificationCampaign,
    NotificationMessage,
    NotificationTemplate,
    SocialIdentity,
    TrustedDevice,
)
from accounts.services.device_session_service import DeviceSessionService

logger = logging.getLogger(__name__)
User = get_user_model()


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


class NotificationService:
    @staticmethod
    def _phone_identity_queryset():
        return SocialIdentity.objects.filter(provider=SocialIdentity.Provider.PHONE).exclude(provider_uid="")

    @staticmethod
    def _phone_number_for_user(user: User) -> str:
        identity = NotificationService._phone_identity_queryset().filter(user_id=user.id).first()
        return (identity.provider_uid if identity else "") or ""

    @staticmethod
    def _q_user_has_apns_notification_allowed() -> Q:
        """APNs：当前 ACTIVE 设备会话对应设备在系统侧已允许通知。"""
        return Q(
            device_sessions__status=AccountDeviceSession.Status.ACTIVE,
            device_sessions__trusted_device__notifications_enabled=True,
        )

    @staticmethod
    def _q_user_has_push_capable_apns() -> Q:
        """APNs：当前 ACTIVE 设备会话对应 TrustedDevice 可推送。"""
        return Q(
            device_sessions__status=AccountDeviceSession.Status.ACTIVE,
            device_sessions__trusted_device__notifications_enabled=True,
            device_sessions__trusted_device__push_token__isnull=False,
        ) & ~Q(device_sessions__trusted_device__push_token="")

    @staticmethod
    def _q_user_has_email_channel() -> Q:
        """邮箱：已绑定非空邮箱。"""
        return Q(email__isnull=False) & ~Q(email="")

    @staticmethod
    def _q_user_has_sms_channel() -> Q:
        """短信：已绑定非空手机号（PHONE SocialIdentity）。"""
        return Q(
            social_identities__provider=SocialIdentity.Provider.PHONE,
            social_identities__provider_uid__gt="",
        )

    @staticmethod
    def _q_user_has_any_notifiable_channel() -> Q:
        """用户维度：任一通知渠道可用（APNs 允许通知 / 有邮箱 / 有手机号）。"""
        return (
            NotificationService._q_user_has_apns_notification_allowed()
            | NotificationService._q_user_has_email_channel()
            | NotificationService._q_user_has_sms_channel()
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
        """
        通知用户列表筛选（面向后台运营/管理员）。

        - q: 搜索关键词。纯数字时按用户 id 精确匹配；否则模糊匹配 用户名 / 邮箱 / 手机号（PHONE SocialIdentity.provider_uid）。
        - only_enabled: “仅开通通知”（用户维度）。任一渠道可用即入选：
          APNs（当前 ACTIVE 会话设备 notifications_enabled=True）/ 邮箱（非空）/ 短信（已绑手机号）。
        - has_email: 是否“有邮箱”。True 要求 email 非空；False 要求 email 为空/NULL；None 不限制。
        - has_sms: 是否“有短信”。这里等价于：是否存在 provider=phone 的 SocialIdentity 且 provider_uid 非空。
        - has_apns: 是否“有APNs”（可下发推送）。要求 notifications_enabled=True 且 push_token 非空；与 only_enabled 的 APNs 判定不同。
        - is_active: Django User.is_active 状态过滤；None 不限制。
        """
        queryset = User.objects.all().order_by("-date_joined", "-id")
        if q:
            q_stripped = q.strip()
            search_q = Q(
                username__icontains=q_stripped
            ) | Q(email__icontains=q_stripped) | Q(
                social_identities__provider=SocialIdentity.Provider.PHONE,
                social_identities__provider_uid__icontains=q_stripped,
            )
            if q_stripped.isdigit():
                search_q |= Q(id=int(q_stripped))
            queryset = queryset.filter(search_q)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if has_email is True:
            # 有邮箱：非空且非 NULL
            queryset = queryset.exclude(email="").filter(email__isnull=False)
        elif has_email is False:
            # 无邮箱：空串或 NULL
            queryset = queryset.filter(Q(email="") | Q(email__isnull=True))

        if has_sms is True:
            # 有短信：存在 PHONE 身份且 provider_uid 非空（手机号）
            queryset = queryset.filter(social_identities__provider=SocialIdentity.Provider.PHONE).exclude(social_identities__provider_uid="")
        elif has_sms is False:
            # 无短信：排除存在 PHONE 身份的用户
            queryset = queryset.exclude(
                id__in=NotificationService._phone_identity_queryset().values("user_id")
            )

        if has_apns is True:
            # 有 APNs（可推送）：已允许通知且具备 push_token
            queryset = queryset.filter(NotificationService._q_user_has_push_capable_apns())
        elif has_apns is False:
            queryset = queryset.exclude(NotificationService._q_user_has_push_capable_apns())

        if only_enabled:
            # “仅开通通知”：用户维度，任一渠道可用即可
            queryset = queryset.filter(NotificationService._q_user_has_any_notifiable_channel())

        # trusted_devices / social_identities 是 1-N 关系，JOIN 后同一用户可能出现多行，distinct 去重。
        return queryset.distinct()

    @staticmethod
    def list_notification_users(*, q: str = "", page: int = 1, page_size: int = 20, only_enabled: bool = True, has_email: bool | None = None, has_sms: bool | None = None, has_apns: bool | None = None, is_active: bool | None = None) -> dict[str, Any]:
        queryset = NotificationService._filter_user_queryset(
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
            for identity in NotificationService._phone_identity_queryset().filter(user_id__in=user_ids)
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
            stat = stats_map.get(
                user.id,
                {"total_devices": 0, "notifications_enabled_devices": 0, "enabled_push_devices": 0},
            )
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
                        # APNs 渠道：以当前 ACTIVE 会话设备为准
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
    def list_templates() -> list[NotificationTemplate]:
        return list(NotificationTemplate.objects.order_by("-is_active", "name", "id"))

    @staticmethod
    def build_context_for_user(user: User) -> dict[str, str]:
        now = timezone.localtime()
        return {
            "user_id": str(user.id),
            "username": user.username or "",
            "email": (user.email or "").strip(),
            "phone": NotificationService._phone_number_for_user(user),
            "date": now.strftime("%Y-%m-%d"),
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        }

    @staticmethod
    def render_text(template_text: str, context: dict[str, str]) -> str:
        return (template_text or "").format_map(_SafeDict(context))

    @staticmethod
    def build_message_content(*, user: User, template: NotificationTemplate | None, title: str, body: str, payload: dict | None):
        context = NotificationService.build_context_for_user(user)
        raw_title = (template.title_template if template else title) or title or ""
        raw_body = (template.body_template if template else body) or body or ""
        title_rendered = NotificationService.render_text(raw_title, context)
        body_rendered = NotificationService.render_text(raw_body, context)

        payload_rendered = dict(template.payload_template) if template and isinstance(template.payload_template, dict) else {}
        if payload:
            payload_rendered.update(payload)
        return title_rendered, body_rendered, payload_rendered

    @staticmethod
    def resolve_target_user_ids(*, user_id: int | None = None, user_ids: list[int] | None = None, filters: dict | None = None) -> list[int]:
        if user_id:
            return [int(user_id)]
        if user_ids:
            return sorted({int(i) for i in user_ids if i})

        filters = filters or {}
        queryset = NotificationService._filter_user_queryset(
            q=(filters.get("q") or "").strip(),
            only_enabled=bool(filters.get("only_enabled", False)),
            has_email=filters.get("has_email"),
            has_sms=filters.get("has_sms"),
            has_apns=filters.get("has_apns"),
            is_active=filters.get("is_active"),
        )
        return list(queryset.values_list("id", flat=True))

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
        target_user_ids = NotificationService.resolve_target_user_ids(user_id=user_id, user_ids=user_ids, filters=filters)
        if not target_user_ids:
            raise ValueError("no_target_users")

        template = NotificationTemplate.objects.filter(id=template_id).first() if template_id else None
        now = timezone.now()
        schedule_time = schedule_at if schedule_at and schedule_at > now else None

        with transaction.atomic():
            campaign = NotificationCampaign.objects.create(
                name=(campaign_name or "").strip(),
                status=NotificationCampaign.Status.SCHEDULED if schedule_time else NotificationCampaign.Status.QUEUED,
                channels=list(dict.fromkeys(channels)),
                title=title or "",
                body=body or "",
                payload=payload or {},
                filters=filters or {},
                target_user_ids=target_user_ids,
                target_count=len(target_user_ids),
                template=template,
                created_by_id=created_by_id,
                request_id=request_id or "",
                scheduled_at=schedule_time,
            )

            from accounts.notification_tasks import send_notification_campaign_task

            async_result = send_notification_campaign_task.apply_async(
                args=[campaign.id, request_id or ""],
                eta=schedule_time,
            )
            campaign.task_id = getattr(async_result, "id", "") or ""
            campaign.save(update_fields=["task_id", "updated_at"])

        return campaign

    @staticmethod
    def execute_campaign(*, campaign_id: int, request_id: str = "", task_id: str = "") -> dict[str, Any]:
        with transaction.atomic():
            campaign = NotificationCampaign.objects.select_for_update().filter(id=campaign_id).first()
            if campaign is None:
                raise ValueError("campaign_not_found")
            if campaign.status in {NotificationCampaign.Status.COMPLETED, NotificationCampaign.Status.FAILED}:
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

        users = list(User.objects.filter(id__in=campaign.target_user_ids).order_by("id"))
        channel_stats = defaultdict(lambda: {"target": 0, "success": 0, "failure": 0})

        for user in users:
            title_rendered, body_rendered, payload_rendered = NotificationService.build_message_content(
                user=user,
                template=campaign.template,
                title=campaign.title,
                body=campaign.body,
                payload=campaign.payload,
            )
            logs = NotificationService.send_to_user_sync(
                campaign_id=campaign.id,
                user_id=user.id,
                channels=campaign.channels,
                title=title_rendered,
                body=body_rendered,
                payload=payload_rendered,
                created_by_id=campaign.created_by_id,
                request_id=request_id or campaign.request_id,
            )
            for log in logs:
                channel_stats[log.channel]["target"] += int(log.target_count or 0)
                channel_stats[log.channel]["success"] += int(log.success_count or 0)
                channel_stats[log.channel]["failure"] += int(log.failure_count or 0)

        success_total = sum(v["success"] for v in channel_stats.values())
        failure_total = sum(v["failure"] for v in channel_stats.values())
        final_status = NotificationCampaign.Status.COMPLETED if success_total > 0 else NotificationCampaign.Status.FAILED

        NotificationCampaign.objects.filter(id=campaign.id).update(
            status=final_status,
            success_count=success_total,
            failure_count=failure_total,
            finished_at=timezone.now(),
            error_message="" if final_status == NotificationCampaign.Status.COMPLETED else "all_channels_failed",
            updated_at=timezone.now(),
        )

        return {
            "campaign_id": campaign.id,
            "status": final_status,
            "target_count": campaign.target_count,
            "success_count": success_total,
            "failure_count": failure_total,
            "channel_stats": channel_stats,
            "task_id": campaign.task_id,
            "request_id": campaign.request_id,
        }

    @staticmethod
    def send_to_user_sync(*, campaign_id: int | None, user_id: int, channels: list[str], title: str, body: str, payload: dict | None, created_by_id: int | None, request_id: str = "") -> list[NotificationMessage]:
        user = User.objects.filter(id=user_id).first()
        if user is None:
            raise ValueError("user_not_found")

        payload = payload or {}
        out: list[NotificationMessage] = []
        for channel in channels:
            if channel == NotificationMessage.Channel.APNS:
                out.append(NotificationService._send_apns(campaign_id=campaign_id, user=user, title=title, body=body, payload=payload, created_by_id=created_by_id, request_id=request_id))
            elif channel == NotificationMessage.Channel.EMAIL:
                out.append(NotificationService._send_email(campaign_id=campaign_id, user=user, title=title, body=body, payload=payload, created_by_id=created_by_id, request_id=request_id))
            elif channel == NotificationMessage.Channel.SMS:
                out.append(NotificationService._send_sms(campaign_id=campaign_id, user=user, title=title, body=body, payload=payload, created_by_id=created_by_id, request_id=request_id))
        return out

    @staticmethod
    def _send_apns(*, campaign_id: int | None, user: User, title: str, body: str, payload: dict, created_by_id: int | None, request_id: str) -> NotificationMessage:
        active_device = DeviceSessionService.apns_trusted_device_for_user(user=user)
        devices = [active_device] if active_device else []
        details: list[dict[str, Any]] = []
        success_count = 0
        failure_count = 0
        topic = (payload.get("apns_topic") or "").strip() if isinstance(payload, dict) else ""
        provider_message_id = ""

        if not devices:
            return NotificationMessage.objects.create(
                campaign_id=campaign_id,
                user_id=user.id,
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

        return NotificationMessage.objects.create(
            campaign_id=campaign_id,
            user_id=user.id,
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
            error_message=error_message,
            created_by_id=created_by_id,
            request_id=request_id or "",
            sent_at=timezone.now(),
        )

    @staticmethod
    def _send_email(*, campaign_id: int | None, user: User, title: str, body: str, payload: dict, created_by_id: int | None, request_id: str) -> NotificationMessage:
        to = (user.email or "").strip()
        if not to:
            return NotificationMessage.objects.create(
                campaign_id=campaign_id,
                user_id=user.id,
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

        ok, reason, provider_message_id, smtp_detail = EmailProvider.send_notification(
            email=to, title=title, body=body, request_id=request_id
        )
        err_msg = ""
        if not ok:
            detail = (smtp_detail or "").strip()
            base = reason or "email_send_failed"
            err_msg = f"{base}: {detail}".strip(": ").strip() if detail else base
            err_msg = err_msg[:2000]

        return NotificationMessage.objects.create(
            campaign_id=campaign_id,
            user_id=user.id,
            channel=NotificationMessage.Channel.EMAIL,
            status=NotificationMessage.Status.SENT if ok else NotificationMessage.Status.FAILED,
            title=title or "",
            body=body or "",
            payload=payload,
            target_count=1,
            success_count=1 if ok else 0,
            failure_count=0 if ok else 1,
            receiver_email=to,
            provider_message_id=provider_message_id,
            error_message="" if ok else err_msg,
            created_by_id=created_by_id,
            request_id=request_id or "",
            sent_at=timezone.now(),
        )

    @staticmethod
    def _send_sms(*, campaign_id: int | None, user: User, title: str, body: str, payload: dict, created_by_id: int | None, request_id: str) -> NotificationMessage:
        to = NotificationService._phone_number_for_user(user)
        if not to:
            return NotificationMessage.objects.create(
                campaign_id=campaign_id,
                user_id=user.id,
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

        ok, reason, provider_message_id = AliyunSMSProvider.send(phone_number=to, title=title, body=body)
        return NotificationMessage.objects.create(
            campaign_id=campaign_id,
            user_id=user.id,
            channel=NotificationMessage.Channel.SMS,
            status=NotificationMessage.Status.SENT if ok else NotificationMessage.Status.FAILED,
            title=title or "",
            body=body or "",
            payload=payload,
            target_count=1,
            success_count=1 if ok else 0,
            failure_count=0 if ok else 1,
            receiver_phone=to,
            provider_message_id=provider_message_id,
            error_message="" if ok else reason,
            created_by_id=created_by_id,
            request_id=request_id or "",
            sent_at=timezone.now(),
        )
