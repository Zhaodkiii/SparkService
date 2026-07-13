"""远程邀请通知投递：APNs → 邮件 → 短信，第一个成功即停止。

职责划分
---------
- `create_invite_and_notify`: 创建邀请并同步投递通知，返回 (invite, DeliveryResult)。
- `_deliver`:               顺序尝试各通道，写入 MemberShareInviteDeliveryLog。
- `DeliveryResult`:         不可变投递结果摘要，供 view 层直接序列化。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from notification_center.models import NotificationMessage
from notification_center.services import NotificationCenterService

from medical.models import Member, MemberShareInvite, MemberShareInviteDeliveryLog
from medical.services import member_binding_service as binding_service
from medical.services.member_invite_service import (
    InviteError,
    _mask_contact,
    create_invite,
)


def _is_email(contact: str) -> bool:
    return "@" in (contact or "")

logger = logging.getLogger("medical.invite_delivery")


# ---------------------------------------------------------------------------
# Messages (i18n 占位：实际文案由客户端 L10n 渲染，服务端仅提供键名/英文兜底)
# ---------------------------------------------------------------------------

_MSG_APP = "邀请成功，已通过应用通知用户"
_MSG_EMAIL = "邀请成功，已邮件通知用户"
_MSG_SMS = "邀请成功，已短信通知用户"
_MSG_FAILED = "分享成功，但通知用户失败，请主动联系用户进入应用查看邀请"

_CH_APP = "app_notification"
_CH_EMAIL = "email"
_CH_SMS = "sms"
_CH_NONE = "none"


@dataclass(frozen=True)
class DeliveryResult:
    delivery_channel: str
    delivery_status: str   # "sent" | "failed"
    display_message: str
    open_url: str = ""
    delivery_failure_code: str = ""
    delivery_failure_message: str = ""

    def api_msg(self) -> str:
        """Top-level `msg` for invite create response (stable machine keys)."""
        if self.delivery_status == "sent":
            return f"invite_sent_by_{self.delivery_channel}"
        if self.delivery_channel == _CH_NONE:
            return "invite_created_delivery_failed_all_channels"
        return f"invite_created_{self.delivery_channel}_delivery_failed"

    def to_dict(self) -> dict:
        d = {
            "delivery_channel": self.delivery_channel,
            "delivery_status": self.delivery_status,
            "display_message": self.display_message,
            "open_url": self.open_url,
        }
        if self.delivery_failure_code:
            d["delivery_failure_code"] = self.delivery_failure_code
        if self.delivery_failure_message:
            d["delivery_failure_message"] = self.delivery_failure_message[:500]
        return d


def _open_url(invite_id: int) -> str:
    return f"spark://member-invite?id={invite_id}"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def create_invite_and_notify(
    *,
    member: Member,
    inviter,
    target_user=None,
    target_contact: str,
    channel: str,
    role: str,
) -> tuple[MemberShareInvite, DeliveryResult]:
    """创建邀请并同步投递通知；支持 target_user=None（无账号，按联系方式直投）。"""
    invite = _create_invite_flexible(
        member=member,
        inviter=inviter,
        target_user=target_user,
        target_contact=target_contact,
        channel=channel,
        role=role,
    )
    result = _deliver(invite, delivery_contact=target_contact)
    return invite, result


# ---------------------------------------------------------------------------
# Invite creation (supports anonymous contact)
# ---------------------------------------------------------------------------

@transaction.atomic
def _create_invite_flexible(
    *,
    member: Member,
    inviter,
    target_user,
    target_contact: str,
    channel: str,
    role: str,
) -> MemberShareInvite:
    """Wrapper that allows target_user=None for contact-only invites."""
    if target_user is not None:
        return create_invite(
            member=member,
            inviter=inviter,
            target_user=target_user,
            channel=channel,
            role=role,
            target_contact=target_contact,
        )

    # No Spark account — create invite record with target_user=None.
    from datetime import timedelta
    from django.utils import timezone
    from medical.models import UserMemberBinding

    try:
        binding_service.ensure_can_share_member(user=inviter, member_id=member.id)
    except PermissionError as exc:
        raise exc

    from medical.services.member_invite_service import resolve_invite_role

    resolved_role = resolve_invite_role(role)
    if resolved_role not in (
        UserMemberBinding.Role.VIEWER,
        UserMemberBinding.Role.EDITOR,
        UserMemberBinding.Role.ADMIN,
    ):
        resolved_role = UserMemberBinding.Role.EDITOR

    masked = _mask_contact(channel, target_contact)
    existing = (
        MemberShareInvite.objects.select_for_update()
        .filter(
            member=member,
            inviter_user=inviter,
            target_user__isnull=True,
            channel=channel,
            role=resolved_role,
            target_contact=masked,
            status=MemberShareInvite.Status.PENDING,
        )
        .first()
    )
    if existing:
        return existing

    return MemberShareInvite.objects.create(
        member=member,
        inviter_user=inviter,
        target_user=None,
        target_contact=masked,
        channel=channel,
        role=resolved_role,
        status=MemberShareInvite.Status.PENDING,
        expires_at=timezone.now() + timedelta(days=7),
    )


# ---------------------------------------------------------------------------
# Delivery orchestration
# ---------------------------------------------------------------------------

def _deliver(invite: MemberShareInvite, *, delivery_contact: str = "") -> DeliveryResult:
    request_id = str(uuid.uuid4())
    open_url = _open_url(invite.id)

    if invite.target_user_id:
        # APNs first
        ok, msg_id, error = _try_apns(invite, request_id)
        if ok:
            _log(invite, MemberShareInviteDeliveryLog.Channel.APNS, MemberShareInviteDeliveryLog.Status.SENT, msg_id)
            return DeliveryResult(_CH_APP, "sent", _MSG_APP, open_url)
        _log(invite, MemberShareInviteDeliveryLog.Channel.APNS, MemberShareInviteDeliveryLog.Status.FAILED, msg_id, error_code=error)

        # Email second
        ok, msg_id, error = _try_email_user(invite, request_id)
        if ok:
            _log(invite, MemberShareInviteDeliveryLog.Channel.EMAIL, MemberShareInviteDeliveryLog.Status.SENT, msg_id)
            return DeliveryResult(_CH_EMAIL, "sent", _MSG_EMAIL, open_url)
        _log(invite, MemberShareInviteDeliveryLog.Channel.EMAIL, MemberShareInviteDeliveryLog.Status.FAILED, msg_id, error_code=error)

        # SMS third
        ok, msg_id, error = _try_sms_user(invite, request_id)
        if ok:
            _log(invite, MemberShareInviteDeliveryLog.Channel.SMS, MemberShareInviteDeliveryLog.Status.SENT, msg_id)
            return DeliveryResult(_CH_SMS, "sent", _MSG_SMS, open_url)
        _log(invite, MemberShareInviteDeliveryLog.Channel.SMS, MemberShareInviteDeliveryLog.Status.FAILED, msg_id, error_code=error)

    else:
        # No Spark account — try direct contact delivery (use plaintext, not DB-masked contact).
        contact = (delivery_contact or invite.target_contact or "").strip()
        if _is_email(contact):
            ok, msg_id, err_code, err_detail = _try_email_direct(invite, contact, request_id)
            if ok:
                _log(invite, MemberShareInviteDeliveryLog.Channel.EMAIL, MemberShareInviteDeliveryLog.Status.SENT, msg_id)
                return DeliveryResult(_CH_EMAIL, "sent", _MSG_EMAIL, open_url)
            _log(
                invite,
                MemberShareInviteDeliveryLog.Channel.EMAIL,
                MemberShareInviteDeliveryLog.Status.FAILED,
                msg_id,
                error_code=err_code,
                error_message=err_detail,
            )
            return DeliveryResult(
                _CH_EMAIL,
                "failed",
                _MSG_FAILED,
                open_url,
                delivery_failure_code=err_code,
                delivery_failure_message=err_detail[:500],
            )
        else:
            ok, msg_id, error = _try_sms_direct(invite, contact, request_id)
            if ok:
                _log(invite, MemberShareInviteDeliveryLog.Channel.SMS, MemberShareInviteDeliveryLog.Status.SENT, msg_id)
                return DeliveryResult(_CH_SMS, "sent", _MSG_SMS, open_url)
            _log(invite, MemberShareInviteDeliveryLog.Channel.SMS, MemberShareInviteDeliveryLog.Status.FAILED, msg_id, error_code=error)
            err_code = error if error and len(error) <= 64 else "sms_delivery_failed"
            return DeliveryResult(
                _CH_SMS,
                "failed",
                _MSG_FAILED,
                open_url,
                delivery_failure_code=err_code,
                delivery_failure_message=error[:500] if error else "",
            )

    _log(invite, MemberShareInviteDeliveryLog.Channel.NONE, MemberShareInviteDeliveryLog.Status.FAILED, "")
    return DeliveryResult(_CH_NONE, "failed", _MSG_FAILED, open_url)


# ---------------------------------------------------------------------------
# Channel helpers
# ---------------------------------------------------------------------------

def _apns_payload(invite: MemberShareInvite) -> dict:
    return {
        "type": "member_invite",
        "route": "member_invite",
        "invite_id": str(invite.id),
        "member_id": str(invite.member_id),
    }


def _invite_title(invite: MemberShareInvite) -> str:
    inviter_name = getattr(invite.inviter_user, "username", "") or f"用户{invite.inviter_user_id}"
    return "成员绑定邀请"


def _invite_body(invite: MemberShareInvite) -> str:
    inviter_name = getattr(invite.inviter_user, "username", "") or f"用户{invite.inviter_user_id}"
    member_name = getattr(invite.member, "name", "") if hasattr(invite, "member") else ""
    if member_name:
        return f"{inviter_name} 邀请你绑定成员 {member_name}"
    return f"{inviter_name} 邀请你绑定成员"


def _try_apns(invite: MemberShareInvite, request_id: str) -> tuple[bool, str, str]:
    """Try sending APNs via NotificationService (creates NotificationMessage). Returns (ok, msg_id, error)."""
    if invite.target_user_id is None:
        return False, "", "no_target_user"

    msgs = NotificationCenterService.send_to_user_sync(
        campaign_id=None,
        user_id=invite.target_user_id,
        channels=[NotificationMessage.Channel.APNS],
        title=_invite_title(invite),
        body=_invite_body(invite),
        payload=_apns_payload(invite),
        created_by_id=invite.inviter_user_id,
        request_id=request_id,
        business_scene="medical.member.invite_received",
        business_reference_type="member_share_invite",
        business_id=str(invite.id),
        idempotency_key=f"medical.member.invite_received:{invite.id}:apns:{invite.target_user_id}",
        source="medical.member_invite_delivery",
        actor_type="user",
        actor_id=str(invite.inviter_user_id),
    )
    msg = msgs[0] if msgs else None
    ok = msg and msg.status in (
        NotificationMessage.Status.ACCEPTED,
        NotificationMessage.Status.DELIVERED,
        NotificationMessage.Status.SENT,
        NotificationMessage.Status.PARTIAL,
    )
    if ok:
        return True, getattr(msg, "provider_message_id", "") or "", ""
    error = ""
    if msg and msg.status == NotificationMessage.Status.SKIPPED:
        error = "no_push_enabled_device"
    elif msg and msg.status == NotificationMessage.Status.FAILED:
        error = "all_devices_failed"
    return False, getattr(msg, "provider_message_id", "") or "", error


def _try_email_user(invite: MemberShareInvite, request_id: str) -> tuple[bool, str, str]:
    """Try sending email via NotificationService (creates NotificationMessage). Returns (ok, msg_id, error)."""
    if invite.target_user_id is None:
        return False, "", "no_target_user"

    open_url = _open_url(invite.id)
    body = f"{_invite_body(invite)}\n\n打开 Spark 查看邀请：{open_url}"
    msgs = NotificationCenterService.send_to_user_sync(
        campaign_id=None,
        user_id=invite.target_user_id,
        channels=[NotificationMessage.Channel.EMAIL],
        title=_invite_title(invite),
        body=body,
        payload=_apns_payload(invite),
        created_by_id=invite.inviter_user_id,
        request_id=request_id,
        business_scene="medical.member.invite_received",
        business_reference_type="member_share_invite",
        business_id=str(invite.id),
        idempotency_key=f"medical.member.invite_received:{invite.id}:email:{invite.target_user_id}",
        source="medical.member_invite_delivery",
        actor_type="user",
        actor_id=str(invite.inviter_user_id),
    )
    msg = msgs[0] if msgs else None
    ok = msg and msg.status in (
        NotificationMessage.Status.ACCEPTED,
        NotificationMessage.Status.DELIVERED,
        NotificationMessage.Status.SENT,
    )
    if ok:
        return True, getattr(msg, "provider_message_id", "") or "", ""
    error = "email_missing" if msg and msg.status == NotificationMessage.Status.SKIPPED else ""
    return False, getattr(msg, "provider_message_id", "") or "", error


def _try_email_direct(invite: MemberShareInvite, email: str, request_id: str) -> tuple[bool, str, str, str]:
    open_url = _open_url(invite.id)
    title = _invite_title(invite)
    body = f"{_invite_body(invite)}\n\n打开 Spark 查看邀请：{open_url}"
    ok, code, msg_id, detail = NotificationCenterService.send_contact_email(
        email=email,
        title=title,
        body=body,
        request_id=request_id,
        business_scene="medical.member.invite_received",
        business_reference_type="member_share_invite",
        business_id=str(invite.id),
        idempotency_key=f"medical.member.invite_received:{invite.id}:direct_email",
        source="medical.member_invite_delivery",
    )
    return ok, msg_id, code, detail


def _try_sms_user(invite: MemberShareInvite, request_id: str) -> tuple[bool, str, str]:
    """Try sending SMS via NotificationService (creates NotificationMessage). Returns (ok, msg_id, error)."""
    if invite.target_user_id is None:
        return False, "", "no_target_user"

    open_url = _open_url(invite.id)
    sms_body = f"你收到一条 Spark 成员绑定邀请，点击打开：{open_url}"
    msgs = NotificationCenterService.send_to_user_sync(
        campaign_id=None,
        user_id=invite.target_user_id,
        channels=[NotificationMessage.Channel.SMS],
        title=_invite_title(invite),
        body=sms_body,
        payload=_apns_payload(invite),
        created_by_id=invite.inviter_user_id,
        request_id=request_id,
        business_scene="medical.member.invite_received",
        business_reference_type="member_share_invite",
        business_id=str(invite.id),
        idempotency_key=f"medical.member.invite_received:{invite.id}:sms:{invite.target_user_id}",
        source="medical.member_invite_delivery",
        actor_type="user",
        actor_id=str(invite.inviter_user_id),
    )
    msg = msgs[0] if msgs else None
    ok = msg and msg.status in (
        NotificationMessage.Status.ACCEPTED,
        NotificationMessage.Status.DELIVERED,
        NotificationMessage.Status.SENT,
    )
    if ok:
        return True, getattr(msg, "provider_message_id", "") or "", ""
    error = "phone_missing" if msg and msg.status == NotificationMessage.Status.SKIPPED else ""
    return False, getattr(msg, "provider_message_id", "") or "", error


def _try_sms_direct(invite: MemberShareInvite, phone: str, request_id: str) -> tuple[bool, str, str]:
    open_url = _open_url(invite.id)
    body = f"你收到一条 Spark 成员绑定邀请，点击打开：{open_url}"
    ok, reason, msg_id = NotificationCenterService.send_contact_sms(
        phone_number=phone,
        title="成员绑定邀请",
        body=body,
        request_id=request_id,
        business_scene="medical.member.invite_received",
        business_reference_type="member_share_invite",
        business_id=str(invite.id),
        idempotency_key=f"medical.member.invite_received:{invite.id}:direct_sms",
        source="medical.member_invite_delivery",
    )
    return ok, msg_id, reason


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _split_delivery_error(value: str) -> tuple[str, str]:
    text = (value or "").strip()
    if not text:
        return "", ""
    if len(text) <= 64:
        return text, ""
    return "delivery_error", text[:2000]


def _log(
    invite: MemberShareInvite,
    channel: str,
    status: str,
    provider_message_id: str,
    error_code: str = "",
    error_message: str = "",
) -> MemberShareInviteDeliveryLog:
    code = (error_code or "").strip()
    message = (error_message or "").strip()
    if code and not message:
        code, message = _split_delivery_error(code)
    elif code and len(code) > 64:
        overflow = code
        code = "delivery_error"
        message = overflow[:2000] if not message else message

    return MemberShareInviteDeliveryLog.objects.create(
        invite=invite,
        channel=channel,
        status=status,
        provider_message_id=provider_message_id or "",
        error_code=code,
        error_message=message,
    )
