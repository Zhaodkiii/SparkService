"""成员远程分享邀请：创建、查询、接受、拒绝、取消与过期。"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import SocialIdentity
from accounts.services.phone_number_service import PhoneNumberService
from common.exceptions import APIError
from medical.models import Member, MemberShareInvite, UserMemberBinding
from medical.services import member_binding_service as binding_service
from medical.services.member_permission_levels import resolve_share_role_from_request


INVITE_TTL = timedelta(days=7)
MAX_PENDING_INVITES_PER_INVITER_PER_DAY = 20
logger = logging.getLogger("medical.invite")


class InviteError(ValueError):
    pass


def _mask_contact(channel: str, contact: str) -> str:
    value = (contact or "").strip()
    if not value:
        return ""
    if channel == MemberShareInvite.Channel.EMAIL and "@" in value:
        local, domain = value.split("@", 1)
        masked_local = (local[:1] + "***") if local else "***"
        return f"{masked_local}@{domain}"
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) >= 7:
        return f"{digits[:3]}****{digits[-2:]}"
    if len(value) <= 2:
        return "***"
    return value[:1] + "***"


def normalize_phone_for_lookup(*, phone: str, country_code: str = "") -> str:
    """将用户输入规范为 E.164；失败抛出 APIError。"""
    raw = (phone or "").strip()
    if not raw:
        raise APIError("phone_number required", code=40031, status_code=400)

    if raw.startswith("+") or raw.startswith("00"):
        return PhoneNumberService.normalize_e164(raw)

    cc = (country_code or "+86").strip()
    if not cc.startswith("+"):
        cc = f"+{cc.lstrip('+')}"
    digits = "".join(ch for ch in raw if ch.isdigit())
    return PhoneNumberService.normalize_e164(f"{cc}{digits}")


def _resolve_user_by_email(*, normalized_email: str, bundle_id: str) -> User | None:
    """按邮箱解析用户：先查 auth_user.email 候选，再用 SocialIdentity.bundle_id 确认当前 App 用户。"""
    normalized_bundle_id = (bundle_id or "").strip()
    if not normalized_bundle_id or not normalized_email:
        return None

    candidate_ids = list(User.objects.filter(email__iexact=normalized_email).values_list("id", flat=True))
    if not candidate_ids:
        return None

    identity = (
        SocialIdentity.objects.filter(
            user_id__in=candidate_ids,
            bundle_id=normalized_bundle_id,
        )
        .select_related("user")
        .order_by("id")
        .first()
    )
    return identity.user if identity else None


def _normalize_email_for_lookup(contact: str) -> str:
    return (contact or "").strip().lower()


def resolve_user_by_contact(
    *,
    channel: str,
    contact: str,
    country_code: str = "",
    bundle_id: str = "",
) -> tuple[User | None, str]:
    """按联系方式解析用户；返回 (user, normalized_contact)。必须按 bundle_id 隔离，禁止跨 App 命中。"""
    normalized_bundle_id = (bundle_id or "").strip()
    normalized = (contact or "").strip()
    if not normalized:
        return None, ""

    if channel == MemberShareInvite.Channel.EMAIL:
        normalized = _normalize_email_for_lookup(normalized)
        if not normalized_bundle_id:
            return None, normalized

        candidate = _resolve_user_by_email(normalized_email=normalized, bundle_id=normalized_bundle_id)
        if candidate:
            logger.info(
                "member_invite.contact_matched",
                extra={
                    "channel": channel,
                    "bundle_id": normalized_bundle_id,
                    "matched_user_id": candidate.id,
                },
            )
            return candidate, normalized
        return None, normalized

    if channel == MemberShareInvite.Channel.PHONE:
        try:
            e164 = normalize_phone_for_lookup(phone=normalized, country_code=country_code)
        except APIError:
            return None, normalized

        if not normalized_bundle_id:
            return None, e164

        identity = (
            SocialIdentity.objects.filter(
                bundle_id=normalized_bundle_id,
                provider=SocialIdentity.Provider.PHONE,
                provider_uid=e164,
            )
            .select_related("user")
            .first()
        )
        if identity:
            logger.info(
                "member_invite.contact_matched",
                extra={
                    "channel": channel,
                    "bundle_id": normalized_bundle_id,
                    "matched_user_id": identity.user_id,
                },
            )
            return identity.user, e164

        return None, e164

    return None, normalized


def resolve_invite_role(role: str | None, permission: str | None = None) -> str:
    data = {}
    if role:
        data["role"] = role
    if permission:
        data["permission"] = permission
    return resolve_share_role_from_request(data)


def expire_stale_invites() -> int:
    now = timezone.now()
    updated = (
        MemberShareInvite.objects.filter(status=MemberShareInvite.Status.PENDING, expires_at__lt=now)
        .update(status=MemberShareInvite.Status.EXPIRED, updated_at=now)
    )
    return updated


def pending_invites_for_user(user: User) -> list[MemberShareInvite]:
    expire_stale_invites()
    now = timezone.now()
    return list(
        MemberShareInvite.objects.filter(
            target_user=user,
            status=MemberShareInvite.Status.PENDING,
            expires_at__gte=now,
            member__is_deleted=False,
        )
        .select_related("member", "inviter_user")
        .order_by("expires_at", "id")
    )


def _ensure_invite_active(invite: MemberShareInvite) -> None:
    if invite.status != MemberShareInvite.Status.PENDING:
        raise InviteError("invite_not_pending")
    if invite.expires_at < timezone.now():
        invite.status = MemberShareInvite.Status.EXPIRED
        invite.save(update_fields=["status", "updated_at"])
        raise InviteError("invite_expired")


@transaction.atomic
def create_invite(
    *,
    member: Member,
    inviter: User,
    target_user: User,
    channel: str,
    role: str,
    target_contact: str = "",
) -> MemberShareInvite:
    expire_stale_invites()
    if target_user.id == inviter.id:
        raise InviteError("cannot_invite_self")

    binding_service.ensure_can_share_member(user=inviter, member_id=member.id)

    if binding_service.get_active_binding(user=target_user, member_id=member.id):
        raise InviteError("already_bound")

    since = timezone.now() - timedelta(days=1)
    sent_today = MemberShareInvite.objects.filter(
        inviter_user=inviter,
        created_at__gte=since,
    ).count()
    if sent_today >= MAX_PENDING_INVITES_PER_INVITER_PER_DAY:
        raise InviteError("invite_rate_limited")

    resolved_role = resolve_invite_role(role)
    if resolved_role not in (
        UserMemberBinding.Role.VIEWER,
        UserMemberBinding.Role.EDITOR,
        UserMemberBinding.Role.ADMIN,
    ):
        resolved_role = UserMemberBinding.Role.EDITOR

    masked = _mask_contact(channel, target_contact or target_user.email or "")
    existing = (
        MemberShareInvite.objects.select_for_update()
        .filter(
            member=member,
            inviter_user=inviter,
            target_user=target_user,
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
        target_user=target_user,
        target_contact=masked,
        channel=channel,
        role=resolved_role,
        status=MemberShareInvite.Status.PENDING,
        expires_at=timezone.now() + INVITE_TTL,
    )


@transaction.atomic
def accept_invite(
    *,
    invite: MemberShareInvite,
    acceptor: User,
    relationship: str,
    custom_relationship: str = "",
) -> UserMemberBinding:
    _ensure_invite_active(invite)
    if invite.target_user_id != acceptor.id:
        raise InviteError("invite_target_mismatch")

    binding, _created = binding_service.accept_share_binding(
        user=acceptor,
        member=invite.member,
        relationship=relationship,
        custom_relationship=custom_relationship,
        role=invite.role,
        invited_by=invite.inviter_user,
    )
    invite.status = MemberShareInvite.Status.ACCEPTED
    invite.accepted_at = timezone.now()
    invite.save(update_fields=["status", "accepted_at", "updated_at"])
    return binding


@transaction.atomic
def reject_invite(*, invite: MemberShareInvite, user: User) -> MemberShareInvite:
    _ensure_invite_active(invite)
    if invite.target_user_id != user.id:
        raise InviteError("invite_target_mismatch")
    invite.status = MemberShareInvite.Status.REJECTED
    invite.save(update_fields=["status", "updated_at"])
    return invite


@transaction.atomic
def cancel_invite(*, invite: MemberShareInvite, inviter: User) -> MemberShareInvite:
    _ensure_invite_active(invite)
    if invite.inviter_user_id != inviter.id:
        raise InviteError("invite_inviter_mismatch")
    invite.status = MemberShareInvite.Status.CANCELLED
    invite.save(update_fields=["status", "updated_at"])
    return invite
