"""成员分享票据：签名生成、解析与校验。"""

from __future__ import annotations

from datetime import datetime, timezone

from django.contrib.auth.models import User
from django.core import signing
from django.utils.dateparse import parse_datetime

from medical.models import Member, UserMemberBinding
from medical.services import member_binding_service as binding_service

SIGNER = signing.TimestampSigner(salt="spark-member-share-ticket")
DEFAULT_MAX_AGE_SECONDS = 60 * 60 * 24 * 7  # 7 days


def build_ticket_payload(
    *,
    member_id: int,
    inviter_user_id: int,
    role: str,
    channel: str,
    nonce: str,
) -> dict:
    return {
        "member_id": member_id,
        "inviter_user_id": inviter_user_id,
        "role": role,
        "channel": channel,
        "nonce": nonce,
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }


def sign_ticket(payload: dict) -> str:
    return SIGNER.sign_object(payload, compress=True)


def unsign_ticket(ticket: str, *, max_age: int = DEFAULT_MAX_AGE_SECONDS) -> dict:
    return SIGNER.unsign_object(ticket, max_age=max_age)


def validate_ticket_for_inviter(*, ticket: str, inviter: User) -> dict:
    payload = unsign_ticket(ticket)
    if int(payload.get("inviter_user_id", -1)) != inviter.id:
        raise signing.BadSignature("inviter_mismatch")
    member_id = int(payload["member_id"])
    binding_service.ensure_can_share_member(user=inviter, member_id=member_id)
    return payload


def resolve_ticket(*, ticket: str, acceptor: User) -> dict:
    try:
        payload = unsign_ticket(ticket)
    except signing.BadSignature as exc:
        raise ValueError("share_ticket_invalid") from exc

    member_id = int(payload["member_id"])
    inviter_id = int(payload["inviter_user_id"])
    try:
        member = Member.objects.get(id=member_id, is_deleted=False)
    except Member.DoesNotExist as exc:
        raise ValueError("member_not_found") from exc

    try:
        inviter = User.objects.get(id=inviter_id)
    except User.DoesNotExist as exc:
        raise ValueError("share_ticket_invalid") from exc

    try:
        binding_service.ensure_can_share_member(user=inviter, member_id=member_id)
    except PermissionError as exc:
        raise ValueError("share_expired") from exc

    existing = binding_service.get_active_binding(user=acceptor, member_id=member_id)
    inviter_binding = binding_service.get_active_binding(user=inviter, member_id=member_id)

    return {
        "member": member,
        "inviter": inviter,
        "role": payload.get("role") or UserMemberBinding.Role.VIEWER,
        "channel": payload.get("channel") or "qr",
        "already_bound": existing is not None,
        "existing_binding_id": existing.id if existing else None,
        "inviter_display_name": _inviter_label(inviter),
        "inviter_relationship": inviter_binding.relationship if inviter_binding else "",
        "shared_user_count": binding_service.count_active_bindings(member_id),
    }


def _inviter_label(user: User) -> str:
    full = f"{user.first_name} {user.last_name}".strip()
    if full:
        return full
    return binding_service._masked_user_label(user)
