"""Account login-method list, reauth ticket, bind and change."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from accounts.models import (
    AccountIdentityVerificationTicket,
    EmailOTP,
    PhoneOTP,
    SocialIdentity,
)
from accounts.services.apple_identity_service import AppleIdentityService
from accounts.services.identity_scope_service import IdentityScopeService
from accounts.services.otp_service import OTPService
from accounts.services.phone_number_service import PhoneNumberService
from common.exceptions import APIError

flow_logger = logging.getLogger("accounts.flow")


class AccountIdentityService:
    TICKET_TTL_SECONDS = 300
    MANAGED_PROVIDERS = (
        SocialIdentity.Provider.PHONE,
        SocialIdentity.Provider.EMAIL,
        SocialIdentity.Provider.APPLE,
    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def list_identities(*, user, bundle_id: str) -> dict[str, Any]:
        real_bundle_id = (bundle_id or "").strip()
        identity_scope = IdentityScopeService.resolve(real_bundle_id)
        bound_by_provider = {
            identity.provider: identity
            for identity in SocialIdentity.objects.filter(
                user=user,
                bundle_id=identity_scope,
                provider__in=AccountIdentityService.MANAGED_PROVIDERS,
            )
        }
        identities = []
        for provider in AccountIdentityService.MANAGED_PROVIDERS:
            identity = bound_by_provider.get(provider)
            bound = identity is not None
            identities.append(
                {
                    "provider": provider,
                    "bound": bound,
                    "masked_value": AccountIdentityService.mask_identity(provider, identity.provider_uid)
                    if bound
                    else "",
                    "modifiable": bound and provider != SocialIdentity.Provider.APPLE,
                    "bindable": not bound,
                }
            )
        return {
            "account_id": user.id,
            "bundle_id": real_bundle_id,
            "identity_scope": identity_scope,
            "identities": identities,
        }

    @staticmethod
    def request_verification(
        *,
        user,
        provider: str,
        purpose: str,
        bundle_id: str,
        device_id: str,
        ip_address: str,
        request_id: str,
    ) -> dict[str, Any]:
        AccountIdentityService._validate_purpose(purpose)
        provider = AccountIdentityService._normalize_provider(provider)
        real_bundle_id = (bundle_id or "").strip()
        identity_scope = IdentityScopeService.resolve(real_bundle_id)
        identity = AccountIdentityService._require_bound_identity(
            user=user,
            identity_scope=identity_scope,
            provider=provider,
        )

        if provider == SocialIdentity.Provider.APPLE:
            # Apple reauth is client-driven; request endpoint only confirms readiness.
            return {"provider": provider, "ready": True}

        if provider == SocialIdentity.Provider.PHONE:
            result = OTPService.request_phone_otp(
                phone_number=identity.provider_uid,
                provider_uid="",
                bundle_id=real_bundle_id,
                device_id=device_id or "",
                ip_address=ip_address or "",
                request_id=request_id or "",
                scene="identity_reauth",
                user_id=user.id,
                actor_user_id=user.id,
            )
            return result

        if provider == SocialIdentity.Provider.EMAIL:
            result = OTPService.request_email_otp(
                email=identity.provider_uid,
                provider_uid="",
                bundle_id=real_bundle_id,
                device_id=device_id or "",
                ip_address=ip_address or "",
                request_id=request_id or "",
                scene="identity_reauth",
            )
            return result

        raise APIError("unsupported_provider", code=40070, status_code=400)

    @staticmethod
    @transaction.atomic
    def verify_and_issue_ticket(
        *,
        user,
        provider: str,
        purpose: str,
        bundle_id: str,
        device_id: str,
        request_id: str,
        otp_id: str = "",
        code: str = "",
        identity_token: str = "",
        authorization_code: str = "",
        user_identifier: str = "",
    ) -> dict[str, Any]:
        AccountIdentityService._validate_purpose(purpose)
        provider = AccountIdentityService._normalize_provider(provider)
        real_bundle_id = (bundle_id or "").strip()
        identity_scope = IdentityScopeService.resolve(real_bundle_id)
        identity = AccountIdentityService._require_bound_identity(
            user=user,
            identity_scope=identity_scope,
            provider=provider,
        )

        if provider in (SocialIdentity.Provider.PHONE, SocialIdentity.Provider.EMAIL):
            AccountIdentityService._consume_bound_otp(
                provider=provider,
                provider_uid=identity.provider_uid,
                otp_id=otp_id,
                code=code,
                bundle_id=real_bundle_id,
            )
        elif provider == SocialIdentity.Provider.APPLE:
            AccountIdentityService._verify_apple_belongs_to_user(
                user=user,
                identity=identity,
                identity_token=identity_token,
                real_bundle_id=real_bundle_id,
                request_id=request_id,
            )
        else:
            raise APIError("unsupported_provider", code=40070, status_code=400)

        ticket_plain, expires_in = AccountIdentityService._issue_ticket(
            user=user,
            purpose=purpose,
            verified_provider=provider,
            identity_scope=identity_scope,
            bundle_id=real_bundle_id,
            device_id=device_id or "",
            request_id=request_id or "",
        )
        flow_logger.info(
            "account.identity.ticket.issued",
            extra={
                "action": "account.identity.ticket.issued",
                "request_id": request_id,
                "user_id": user.id,
                "provider": provider,
                "purpose": purpose,
                "identity_scope": identity_scope,
                "bundle_id": real_bundle_id,
            },
        )
        return {"verification_ticket": ticket_plain, "expires_in": expires_in}

    @staticmethod
    @transaction.atomic
    def bind_identity(
        *,
        user,
        provider: str,
        verification_ticket: str,
        bundle_id: str,
        device_id: str,
        request_id: str,
        target: str = "",
        otp_id: str = "",
        code: str = "",
        identity_token: str = "",
        authorization_code: str = "",
        user_identifier: str = "",
    ) -> dict[str, Any]:
        provider = AccountIdentityService._normalize_provider(provider)
        real_bundle_id = (bundle_id or "").strip()
        identity_scope = IdentityScopeService.resolve(real_bundle_id)

        ticket = AccountIdentityService._lock_valid_ticket(
            user=user,
            ticket_plain=verification_ticket,
            purpose=AccountIdentityVerificationTicket.Purpose.BIND_IDENTITY,
            identity_scope=identity_scope,
        )

        if provider == SocialIdentity.Provider.APPLE:
            provider_uid = AccountIdentityService._resolve_apple_provider_uid(
                identity_token=identity_token,
                real_bundle_id=real_bundle_id,
                request_id=request_id,
            )
        elif provider in (SocialIdentity.Provider.PHONE, SocialIdentity.Provider.EMAIL):
            provider_uid = AccountIdentityService.normalize_provider_uid(provider, target)
            AccountIdentityService._consume_target_otp(
                provider=provider,
                provider_uid=provider_uid,
                otp_id=otp_id,
                code=code,
                bundle_id=real_bundle_id,
                error_prefix="target",
            )
        else:
            raise APIError("unsupported_provider", code=40070, status_code=400)

        # Reject if current user already has another identity of this provider.
        existing_own = (
            SocialIdentity.objects.select_for_update()
            .filter(user=user, bundle_id=identity_scope, provider=provider)
            .first()
        )
        if existing_own and existing_own.provider_uid != provider_uid:
            raise APIError(
                "identity_already_bound",
                code=40085,
                status_code=400,
                details={"provider": provider},
            )

        AccountIdentityService.ensure_target_available_or_rebind_inactive(
            user=user,
            identity_scope=identity_scope,
            provider=provider,
            provider_uid=provider_uid,
            request_id=request_id,
            real_bundle_id=real_bundle_id,
            device_id=device_id or "",
        )

        AccountIdentityService._mark_ticket_used(ticket)

        if provider == SocialIdentity.Provider.EMAIL:
            AccountIdentityService._sync_user_email(user=user, email=provider_uid)

        flow_logger.info(
            "account.identity.bind.success",
            extra={
                "action": "account.identity.bind",
                "request_id": request_id,
                "user_id": user.id,
                "provider": provider,
                "identity_scope": identity_scope,
                "bundle_id": real_bundle_id,
                "device_id": device_id or "",
                "masked_target": AccountIdentityService.mask_identity(provider, provider_uid),
            },
        )
        return AccountIdentityService.list_identities(user=user, bundle_id=real_bundle_id)

    @staticmethod
    @transaction.atomic
    def change_identity(
        *,
        user,
        provider: str,
        verification_ticket: str,
        bundle_id: str,
        device_id: str,
        request_id: str,
        new_target: str = "",
        new_otp_id: str = "",
        new_code: str = "",
    ) -> dict[str, Any]:
        provider = AccountIdentityService._normalize_provider(provider)
        if provider == SocialIdentity.Provider.APPLE:
            raise APIError("apple_identity_change_not_supported", code=40071, status_code=400)

        real_bundle_id = (bundle_id or "").strip()
        identity_scope = IdentityScopeService.resolve(real_bundle_id)

        ticket = AccountIdentityService._lock_valid_ticket(
            user=user,
            ticket_plain=verification_ticket,
            purpose=AccountIdentityVerificationTicket.Purpose.CHANGE_IDENTITY,
            identity_scope=identity_scope,
        )

        current = AccountIdentityService._require_bound_identity(
            user=user,
            identity_scope=identity_scope,
            provider=provider,
            for_update=True,
        )

        new_provider_uid = AccountIdentityService.normalize_provider_uid(provider, new_target)
        if new_provider_uid == current.provider_uid:
            AccountIdentityService._mark_ticket_used(ticket)
            return AccountIdentityService.list_identities(user=user, bundle_id=real_bundle_id)

        AccountIdentityService._consume_target_otp(
            provider=provider,
            provider_uid=new_provider_uid,
            otp_id=new_otp_id,
            code=new_code,
            bundle_id=real_bundle_id,
            error_prefix="target",
        )

        # Ensure new target is free or owned by inactive user (then rebind that row away).
        conflicting = AccountIdentityService.get_existing_identity(
            identity_scope=identity_scope,
            provider=provider,
            provider_uid=new_provider_uid,
            for_update=True,
        )
        if conflicting is not None:
            if conflicting.user_id == user.id:
                # Same user already has this uid somehow; keep current row consistent.
                pass
            elif conflicting.user.is_active:
                raise APIError(
                    "identity_already_bound_to_active_user",
                    code=40921,
                    status_code=409,
                    details={
                        "provider": provider,
                        "masked_target": AccountIdentityService.mask_identity(provider, new_provider_uid),
                    },
                )
            else:
                # Release inactive user's claim by deleting that row so unique constraint allows update.
                flow_logger.info(
                    "account.identity.change.release_inactive",
                    extra={
                        "action": "account.identity.change",
                        "request_id": request_id,
                        "old_user_id": conflicting.user_id,
                        "new_user_id": user.id,
                        "provider": provider,
                        "identity_scope": identity_scope,
                        "bundle_id": real_bundle_id,
                        "masked_target": AccountIdentityService.mask_identity(provider, new_provider_uid),
                    },
                )
                conflicting.delete()

        current.provider_uid = new_provider_uid
        current.save(update_fields=["provider_uid", "updated_at"])
        AccountIdentityService._mark_ticket_used(ticket)

        if provider == SocialIdentity.Provider.EMAIL:
            AccountIdentityService._sync_user_email(user=user, email=new_provider_uid)

        # Guard: user must still have at least one managed identity (always true after change).
        remaining = SocialIdentity.objects.filter(
            user=user,
            bundle_id=identity_scope,
            provider__in=AccountIdentityService.MANAGED_PROVIDERS,
        ).count()
        if remaining < 1:
            raise APIError("last_identity_cannot_be_removed", code=40086, status_code=400)

        flow_logger.info(
            "account.identity.change.success",
            extra={
                "action": "account.identity.change",
                "request_id": request_id,
                "user_id": user.id,
                "provider": provider,
                "identity_scope": identity_scope,
                "bundle_id": real_bundle_id,
                "device_id": device_id or "",
                "masked_target": AccountIdentityService.mask_identity(provider, new_provider_uid),
            },
        )
        return AccountIdentityService.list_identities(user=user, bundle_id=real_bundle_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_identity_scope(bundle_id: str) -> str:
        return IdentityScopeService.resolve(bundle_id)

    @staticmethod
    def normalize_provider_uid(provider: str, value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            raise APIError("target_required", code=40072, status_code=400)
        if provider == SocialIdentity.Provider.PHONE:
            return PhoneNumberService.normalize_e164(raw)
        if provider == SocialIdentity.Provider.EMAIL:
            return raw.lower()
        if provider == SocialIdentity.Provider.APPLE:
            return raw
        raise APIError("unsupported_provider", code=40070, status_code=400)

    @staticmethod
    def get_existing_identity(
        *,
        identity_scope: str,
        provider: str,
        provider_uid: str,
        for_update: bool = False,
    ):
        qs = SocialIdentity.objects.select_related("user").filter(
            bundle_id=identity_scope,
            provider=provider,
            provider_uid=provider_uid,
        )
        if for_update:
            qs = qs.select_for_update()
        return qs.first()

    @staticmethod
    def ensure_target_available_or_rebind_inactive(
        *,
        user,
        identity_scope: str,
        provider: str,
        provider_uid: str,
        request_id: str,
        real_bundle_id: str,
        device_id: str,
    ) -> SocialIdentity:
        identity = AccountIdentityService.get_existing_identity(
            identity_scope=identity_scope,
            provider=provider,
            provider_uid=provider_uid,
            for_update=True,
        )
        if identity is None:
            return SocialIdentity.objects.create(
                user=user,
                bundle_id=identity_scope,
                provider=provider,
                provider_uid=provider_uid,
            )

        if identity.user_id == user.id:
            return identity

        if identity.user.is_active:
            raise APIError(
                "identity_already_bound_to_active_user",
                code=40921,
                status_code=409,
                details={
                    "provider": provider,
                    "masked_target": AccountIdentityService.mask_identity(provider, provider_uid),
                },
            )

        old_user_id = identity.user_id
        identity.user = user
        identity.save(update_fields=["user", "updated_at"])
        flow_logger.info(
            "account.identity.rebind_inactive",
            extra={
                "action": "account.identity.rebind_inactive",
                "request_id": request_id,
                "old_user_id": old_user_id,
                "new_user_id": user.id,
                "provider": provider,
                "identity_scope": identity_scope,
                "bundle_id": real_bundle_id,
                "device_id": device_id,
                "masked_target": AccountIdentityService.mask_identity(provider, provider_uid),
            },
        )
        return identity

    @staticmethod
    def mask_identity(provider: str, provider_uid: str) -> str:
        if provider == SocialIdentity.Provider.PHONE:
            return PhoneNumberService.masked_display(provider_uid)
        if provider == SocialIdentity.Provider.EMAIL:
            return AccountIdentityService._mask_email(provider_uid)
        if provider == SocialIdentity.Provider.APPLE:
            return "Apple ID"
        return ""

    @staticmethod
    def _mask_email(email: str) -> str:
        email = (email or "").strip()
        if not email or "@" not in email:
            return "***"
        local, _, domain = email.partition("@")
        if len(local) <= 1:
            return f"*@{domain}"
        if len(local) <= 4:
            return f"{local[0]}***@{domain}"
        return f"{local[:2]}***{local[-1]}@{domain}"

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        value = (provider or "").strip().lower()
        if value not in {
            SocialIdentity.Provider.PHONE,
            SocialIdentity.Provider.EMAIL,
            SocialIdentity.Provider.APPLE,
        }:
            raise APIError("unsupported_provider", code=40070, status_code=400)
        return value

    @staticmethod
    def _validate_purpose(purpose: str) -> str:
        value = (purpose or "").strip()
        allowed = {
            AccountIdentityVerificationTicket.Purpose.BIND_IDENTITY,
            AccountIdentityVerificationTicket.Purpose.CHANGE_IDENTITY,
        }
        if value not in allowed:
            raise APIError("invalid_purpose", code=40073, status_code=400)
        return value

    @staticmethod
    def _require_bound_identity(*, user, identity_scope: str, provider: str, for_update: bool = False):
        qs = SocialIdentity.objects.filter(
            user=user,
            bundle_id=identity_scope,
            provider=provider,
        )
        if for_update:
            qs = qs.select_for_update()
        identity = qs.first()
        if identity is None:
            raise APIError("identity_not_bound", code=40084, status_code=400, details={"provider": provider})
        return identity

    @staticmethod
    def _hash_ticket(ticket_plain: str) -> str:
        return hashlib.sha256(ticket_plain.encode("utf-8")).hexdigest()

    @staticmethod
    def _issue_ticket(
        *,
        user,
        purpose: str,
        verified_provider: str,
        identity_scope: str,
        bundle_id: str,
        device_id: str,
        request_id: str,
    ) -> tuple[str, int]:
        now = timezone.now()
        ticket_plain = secrets.token_urlsafe(32)
        expires_at = now + timedelta(seconds=AccountIdentityService.TICKET_TTL_SECONDS)
        AccountIdentityVerificationTicket.objects.create(
            user=user,
            purpose=purpose,
            verified_provider=verified_provider,
            identity_scope=identity_scope,
            bundle_id=bundle_id or "",
            device_id=device_id or "",
            ticket_hash=AccountIdentityService._hash_ticket(ticket_plain),
            expires_at=expires_at,
            request_id=request_id or "",
        )
        return ticket_plain, AccountIdentityService.TICKET_TTL_SECONDS

    @staticmethod
    def _lock_valid_ticket(*, user, ticket_plain: str, purpose: str, identity_scope: str):
        now = timezone.now()
        ticket_hash = AccountIdentityService._hash_ticket((ticket_plain or "").strip())
        ticket = (
            AccountIdentityVerificationTicket.objects.select_for_update()
            .filter(ticket_hash=ticket_hash)
            .first()
        )
        if ticket is None or ticket.user_id != user.id or ticket.purpose != purpose or ticket.identity_scope != identity_scope:
            raise APIError("verification_ticket_invalid", code=40083, status_code=400)
        if ticket.used_at is not None:
            raise APIError("verification_ticket_used", code=40082, status_code=400)
        if ticket.expires_at <= now:
            raise APIError("verification_ticket_expired", code=40081, status_code=400)
        return ticket

    @staticmethod
    def _mark_ticket_used(ticket):
        ticket.used_at = timezone.now()
        ticket.save(update_fields=["used_at"])

    @staticmethod
    def _consume_ticket(*, user, ticket_plain: str, purpose: str, identity_scope: str):
        ticket = AccountIdentityService._lock_valid_ticket(
            user=user,
            ticket_plain=ticket_plain,
            purpose=purpose,
            identity_scope=identity_scope,
        )
        AccountIdentityService._mark_ticket_used(ticket)
        return ticket

    @staticmethod
    def _consume_bound_otp(*, provider: str, provider_uid: str, otp_id: str, code: str, bundle_id: str):
        AccountIdentityService._consume_target_otp(
            provider=provider,
            provider_uid=provider_uid,
            otp_id=otp_id,
            code=code,
            bundle_id=bundle_id,
            error_prefix="otp",
        )

    @staticmethod
    def _consume_target_otp(
        *,
        provider: str,
        provider_uid: str,
        otp_id: str,
        code: str,
        bundle_id: str,
        error_prefix: str = "target",
    ):
        now = timezone.now()
        if not otp_id or not code:
            raise APIError(f"{error_prefix}_otp_required", code=40074, status_code=400)

        if provider == SocialIdentity.Provider.EMAIL:
            otp = EmailOTP.objects.select_for_update().filter(otp_id=otp_id, email=provider_uid).first()
            if not otp:
                raise APIError(f"{error_prefix}_otp_invalid", code=40075, status_code=400)
            AccountIdentityService._verify_otp_row(
                otp=otp,
                code=code,
                now=now,
                invalid_msg=f"{error_prefix}_otp_invalid",
                expired_msg=f"{error_prefix}_otp_expired",
                invalid_code=40075,
                expired_code=40076,
            )
            return

        if provider == SocialIdentity.Provider.PHONE:
            otp = (
                PhoneOTP.objects.select_for_update()
                .filter(otp_id=otp_id, phone_number=provider_uid)
                .first()
            )
            if not otp:
                raise APIError(f"{error_prefix}_otp_invalid", code=40075, status_code=400)
            if otp.bundle_id and bundle_id and otp.bundle_id != bundle_id:
                raise APIError("bundle_id mismatch", code=40044, status_code=400)
            if getattr(otp, "invalidated_at", None) is not None:
                raise APIError(f"{error_prefix}_otp_invalid", code=40075, status_code=400)
            if otp.send_status in {
                PhoneOTP.SendStatus.QUEUED,
                PhoneOTP.SendStatus.SUBMIT_FAILED,
                PhoneOTP.SendStatus.SUBMIT_UNKNOWN,
            }:
                raise APIError("OTP SMS not sent", code=40046, status_code=400)
            AccountIdentityService._verify_otp_row(
                otp=otp,
                code=code,
                now=now,
                invalid_msg=f"{error_prefix}_otp_invalid",
                expired_msg=f"{error_prefix}_otp_expired",
                invalid_code=40075,
                expired_code=40076,
            )
            return

        raise APIError("unsupported_provider", code=40070, status_code=400)

    @staticmethod
    def _verify_otp_row(*, otp, code: str, now, invalid_msg: str, expired_msg: str, invalid_code: int, expired_code: int):
        if otp.used_at is not None:
            raise APIError(invalid_msg, code=invalid_code, status_code=400)
        if otp.expires_at <= now:
            raise APIError(expired_msg, code=expired_code, status_code=400)
        if otp.locked_until and otp.locked_until > now:
            raise APIError("OTP temporarily locked", code=42301, status_code=423)

        expected_hash = OTPService._hash_code(code)
        if expected_hash != otp.code_hash:
            otp.attempts += 1
            update_fields = ["attempts"]
            if otp.attempts >= OTPService.MAX_ATTEMPTS:
                otp.locked_until = now + timedelta(minutes=OTPService.LOCKOUT_MINUTES)
                update_fields.append("locked_until")
            otp.save(update_fields=update_fields)
            raise APIError(invalid_msg, code=invalid_code, status_code=400)

        otp.used_at = now
        otp.save(update_fields=["used_at"])

    @staticmethod
    def _verify_apple_belongs_to_user(*, user, identity, identity_token: str, real_bundle_id: str, request_id: str):
        if not identity_token:
            raise APIError("identity_token_required", code=40077, status_code=400)
        payload, _matched = AppleIdentityService.verify_identity_token(
            identity_token=identity_token,
            audiences=[real_bundle_id] if real_bundle_id else [],
        )
        subject = (payload.get("sub") or "").strip()
        if not subject or subject != identity.provider_uid:
            raise APIError("apple_identity_mismatch", code=40127, status_code=401)
        if identity.user_id != user.id:
            raise APIError("apple_identity_mismatch", code=40127, status_code=401)
        return payload

    @staticmethod
    def _resolve_apple_provider_uid(*, identity_token: str, real_bundle_id: str, request_id: str) -> str:
        if not identity_token:
            raise APIError("identity_token_required", code=40077, status_code=400)
        payload, _matched = AppleIdentityService.verify_identity_token(
            identity_token=identity_token,
            audiences=[real_bundle_id] if real_bundle_id else [],
        )
        subject = (payload.get("sub") or "").strip()
        if not subject:
            raise APIError("apple_sub_missing", code=40123, status_code=401)
        return subject

    @staticmethod
    def _sync_user_email(*, user, email: str):
        normalized = (email or "").strip().lower()
        if not normalized:
            return
        if (user.email or "").strip().lower() == normalized:
            return
        user.email = normalized
        user.save(update_fields=["email"])
