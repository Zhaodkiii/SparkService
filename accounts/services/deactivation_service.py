import logging

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from common.exceptions import APIError
from accounts.models import (
    AccountDeactivation,
    AccountDeactivationAudit,
    EmailOTP,
    PhoneOTP,
    SocialIdentity,
)
from accounts.services.apple_identity_service import AppleIdentityService
from accounts.services.otp_service import OTPService
from accounts.services.phone_number_service import PhoneNumberService

logger = logging.getLogger(__name__)
flow_logger = logging.getLogger("accounts.flow")


class DeactivationService:
    @staticmethod
    @transaction.atomic
    def verify_deactivation_proof(*, user, verification: dict | None, request_id: str):
        if not verification:
            raise APIError("verification required", code=40061, status_code=400)

        verification_type = (verification.get("type") or "").strip().lower()
        now = timezone.now()

        if verification_type == "apple":
            identity_token = (verification.get("identity_token") or "").strip()
            user_identifier = (verification.get("user_identifier") or "").strip()
            allowed_bundle_ids = getattr(settings, "APPLE_ALLOWED_BUNDLE_IDS", [])
            if not allowed_bundle_ids:
                raise APIError("apple bundle audience not configured", code=40062, status_code=400)
            payload, matched_audience = AppleIdentityService.verify_identity_token(
                identity_token,
                audiences=allowed_bundle_ids,
            )
            subject = (payload.get("sub") or "").strip()
            if not subject or subject != user_identifier:
                raise APIError("apple subject mismatch", code=40161, status_code=401)
            linked = SocialIdentity.objects.filter(
                user=user,
                provider=SocialIdentity.Provider.APPLE,
                provider_uid=subject,
                bundle_id=matched_audience,
            ).exists()
            if not linked:
                raise APIError("apple identity not linked to current user", code=40162, status_code=401)
            return {"type": "apple", "bundle_id": matched_audience}

        if verification_type == "email":
            email = (user.email or "").strip().lower()
            otp_id = (verification.get("otp_id") or "").strip()
            code = (verification.get("code") or "").strip()
            otp = EmailOTP.objects.select_for_update().filter(otp_id=otp_id, email=email).first()
            if not otp:
                raise APIError("OTP not found", code=40461, status_code=404)
            DeactivationService._verify_otp_row(otp=otp, code=code, now=now, invalid_code=40063)
            return {"type": "email", "otp_id": otp_id}

        if verification_type == "phone":
            profile = getattr(user, "profile", None)
            phone_number = getattr(profile, "phone_number", "") if profile else ""
            normalized_phone = PhoneNumberService.normalize_e164(phone_number)
            otp_id = (verification.get("otp_id") or "").strip()
            code = (verification.get("code") or "").strip()
            otp = PhoneOTP.objects.select_for_update().filter(otp_id=otp_id, phone_number=normalized_phone).first()
            if not otp:
                raise APIError("OTP not found", code=40462, status_code=404)
            DeactivationService._verify_otp_row(otp=otp, code=code, now=now, invalid_code=40064)
            return {"type": "phone", "otp_id": otp_id}

        raise APIError("unsupported verification type", code=40065, status_code=400)

    @staticmethod
    def _verify_otp_row(*, otp, code: str, now, invalid_code: int):
        if otp.used_at is not None:
            raise APIError("OTP already used", code=40066, status_code=400)
        if otp.expires_at <= now:
            raise APIError("OTP expired", code=40067, status_code=400)
        if otp.locked_until and otp.locked_until > now:
            raise APIError("OTP temporarily locked", code=42361, status_code=423)

        expected_hash = OTPService._hash_code(code)
        if expected_hash != otp.code_hash:
            otp.attempts += 1
            if otp.attempts >= OTPService.MAX_ATTEMPTS:
                otp.locked_until = now + timedelta(minutes=OTPService.LOCKOUT_MINUTES)
            otp.save(update_fields=["attempts", "locked_until"])
            raise APIError("Invalid OTP", code=invalid_code, status_code=400)

        otp.used_at = now
        otp.save(update_fields=["used_at"])

    @staticmethod
    def request_deactivation(*, user, request_id: str, immediate_deactivation: bool = True, countdown_hours: int = 0):
        flow_logger.info(
            "account.deactivation.service.request.begin",
            extra={"action": "account.deactivation.service.request", "request_id": request_id, "user_id": user.id},
        )
        # Idempotency: reuse active deactivation workflow if one already exists.
        existing = (
            AccountDeactivation.objects.filter(
                user=user,
                state__in=[
                    AccountDeactivation.DeactivationState.REQUESTED,
                    AccountDeactivation.DeactivationState.SCHEDULED,
                    AccountDeactivation.DeactivationState.FROZEN,
                    AccountDeactivation.DeactivationState.ANONYMIZED,
                    AccountDeactivation.DeactivationState.CLEANED_UP,
                ],
            )
            .order_by("-id")
            .first()
        )
        if existing:
            flow_logger.info(
                "account.deactivation.service.request.reused",
                extra={
                    "action": "account.deactivation.service.request",
                    "request_id": request_id,
                    "user_id": user.id,
                    "deactivation_id": existing.id,
                    "state": existing.state,
                },
            )
            return {"deactivation_id": existing.id, "state": existing.state, "reused": True}

        now = timezone.now()
        scheduled_at = now if immediate_deactivation else now + timedelta(hours=max(1, int(countdown_hours or 24)))
        obj = AccountDeactivation.objects.create(
            user=user,
            state=AccountDeactivation.DeactivationState.SCHEDULED,
            requested_at=now,
            scheduled_at=scheduled_at,
            request_id=request_id or "",
        )
        flow_logger.info(
            "account.deactivation.service.request.created",
            extra={
                "action": "account.deactivation.service.request",
                "request_id": request_id,
                "user_id": user.id,
                "deactivation_id": obj.id,
                "state": obj.state,
            },
        )
        return {
            "deactivation_id": obj.id,
            "state": obj.state,
            "scheduled_at": obj.scheduled_at,
            "immediate_deactivation": immediate_deactivation,
            "countdown_hours": 0 if immediate_deactivation else max(1, int(countdown_hours or 24)),
            "reused": False,
        }

    @staticmethod
    @transaction.atomic
    def process_deactivation(*, deactivation_id: int, request_id: str, task_id: str | None = None):
        flow_logger.info(
            "account.deactivation.service.process.begin",
            extra={
                "action": "account.deactivation.service.process",
                "request_id": request_id,
                "deactivation_id": deactivation_id,
                "task_id": task_id or "",
            },
        )
        now = timezone.now()
        obj = (
            AccountDeactivation.objects.select_for_update()
            .filter(id=deactivation_id)
            .first()
        )
        if not obj:
            flow_logger.warning(
                "account.deactivation.service.process.failed",
                extra={
                    "action": "account.deactivation.service.process",
                    "request_id": request_id,
                    "deactivation_id": deactivation_id,
                    "reason": "deactivation_not_found",
                },
            )
            raise APIError("deactivation not found", code=40402, status_code=404)

        if obj.state in (
            AccountDeactivation.DeactivationState.DEACTIVATED,
            AccountDeactivation.DeactivationState.CANCELLED,
        ):
            flow_logger.info(
                "account.deactivation.service.process.noop",
                extra={
                    "action": "account.deactivation.service.process",
                    "request_id": request_id,
                    "deactivation_id": obj.id,
                    "state": obj.state,
                },
            )
            return {"deactivation_id": obj.id, "state": obj.state, "noop": True}

        user = get_user_model().objects.select_for_update().get(id=obj.user_id)
        profile = getattr(user, "profile", None)
        freeze_phone = getattr(profile, "phone_number", "") if profile else ""

        # Step 1: Freeze identifiers (compliance-safe order)
        if obj.state == AccountDeactivation.DeactivationState.SCHEDULED or not obj.freeze_email:
            flow_logger.info(
                "account.deactivation.service.process.step",
                extra={"action": "account.deactivation.service.process", "request_id": request_id, "deactivation_id": obj.id, "step": "freeze_identifiers"},
            )
            AccountDeactivationAudit.objects.create(
                deactivation=obj,
                action=AccountDeactivationAudit.AuditAction.FREEZE_IDENTIFIERS,
                request_id=request_id or "",
                details={"email": user.email, "phone": freeze_phone},
            )
            obj.freeze_email = user.email or ""
            obj.freeze_phone_number = freeze_phone or ""
            obj.processed_at = obj.processed_at or now
            obj.state = AccountDeactivation.DeactivationState.FROZEN
            obj.save(update_fields=["freeze_email", "freeze_phone_number", "processed_at", "state"])

        # Step 2: Anonymize
        if obj.state == AccountDeactivation.DeactivationState.FROZEN:
            flow_logger.info(
                "account.deactivation.service.process.step",
                extra={"action": "account.deactivation.service.process", "request_id": request_id, "deactivation_id": obj.id, "step": "anonymize"},
            )
            AccountDeactivationAudit.objects.create(
                deactivation=obj,
                action=AccountDeactivationAudit.AuditAction.ANONYMIZE,
                request_id=request_id or "",
            )
            obj.state = AccountDeactivation.DeactivationState.ANONYMIZED
            # Ensure unique email value.
            user.email = f"anon+{obj.id}+{int(now.timestamp())}@example.com"
            if profile:
                profile.phone_number = ""
                profile.save(update_fields=["phone_number"])
            user.save(update_fields=["email"])
            obj.save(update_fields=["state"])

        # Step 3: Cleanup (delete by frozen identifiers)
        if obj.state == AccountDeactivation.DeactivationState.ANONYMIZED:
            flow_logger.info(
                "account.deactivation.service.process.step",
                extra={"action": "account.deactivation.service.process", "request_id": request_id, "deactivation_id": obj.id, "step": "cleanup_otps"},
            )
            AccountDeactivationAudit.objects.create(
                deactivation=obj,
                action=AccountDeactivationAudit.AuditAction.CLEANUP_OTPS,
                request_id=request_id or "",
                details={"freeze_email": obj.freeze_email, "freeze_phone_number": obj.freeze_phone_number},
            )
            if obj.freeze_email:
                EmailOTP.objects.filter(email=obj.freeze_email).delete()
            if obj.freeze_phone_number:
                PhoneOTP.objects.filter(phone_number=obj.freeze_phone_number).delete()
            obj.state = AccountDeactivation.DeactivationState.CLEANED_UP
            obj.save(update_fields=["state"])

        # Step 4: Deactivate user
        if obj.state == AccountDeactivation.DeactivationState.CLEANED_UP:
            flow_logger.info(
                "account.deactivation.service.process.step",
                extra={"action": "account.deactivation.service.process", "request_id": request_id, "deactivation_id": obj.id, "step": "deactivate_user"},
            )
            AccountDeactivationAudit.objects.create(
                deactivation=obj,
                action=AccountDeactivationAudit.AuditAction.DEACTIVATE_USER,
                request_id=request_id or "",
            )
            user.is_active = False
            user.save(update_fields=["is_active"])
            obj.state = AccountDeactivation.DeactivationState.DEACTIVATED
            obj.completed_at = now
            obj.save(update_fields=["state", "completed_at"])

        flow_logger.info(
            "account.deactivation.service.process.success",
            extra={
                "action": "account.deactivation.service.process",
                "request_id": request_id,
                "deactivation_id": obj.id,
                "state": obj.state,
            },
        )
        return {"deactivation_id": obj.id, "state": obj.state, "noop": False}

    @staticmethod
    @transaction.atomic
    def mark_failed(*, deactivation_id: int, request_id: str, error_message: str):
        flow_logger.warning(
            "account.deactivation.service.mark_failed.begin",
            extra={
                "action": "account.deactivation.service.mark_failed",
                "request_id": request_id,
                "deactivation_id": deactivation_id,
            },
        )
        obj = (
            AccountDeactivation.objects.select_for_update()
            .filter(id=deactivation_id)
            .first()
        )
        if not obj:
            flow_logger.warning(
                "account.deactivation.service.mark_failed.skip",
                extra={
                    "action": "account.deactivation.service.mark_failed",
                    "request_id": request_id,
                    "deactivation_id": deactivation_id,
                    "reason": "not_found",
                },
            )
            return
        if obj.state in (
            AccountDeactivation.DeactivationState.DEACTIVATED,
            AccountDeactivation.DeactivationState.CANCELLED,
        ):
            flow_logger.info(
                "account.deactivation.service.mark_failed.skip",
                extra={
                    "action": "account.deactivation.service.mark_failed",
                    "request_id": request_id,
                    "deactivation_id": deactivation_id,
                    "reason": "already_terminal",
                    "state": obj.state,
                },
            )
            return

        obj.state = AccountDeactivation.DeactivationState.FAILED
        obj.failed_at = timezone.now()
        obj.error_message = (error_message or "")[:2000]
        obj.save(update_fields=["state", "failed_at", "error_message"])

        AccountDeactivationAudit.objects.create(
            deactivation=obj,
            action=AccountDeactivationAudit.AuditAction.FAILED,
            request_id=request_id or "",
            details={"error": (error_message or "")[:500]},
        )
        flow_logger.error(
            "account.deactivation.service.mark_failed.done",
            extra={
                "action": "account.deactivation.service.mark_failed",
                "request_id": request_id,
                "deactivation_id": deactivation_id,
                "state": obj.state,
                "error_message": (error_message or "")[:500],
            },
        )

    @staticmethod
    @transaction.atomic
    def cancel_deactivation(*, deactivation_id: int, user_id: int, request_id: str, reason: str = ""):
        obj = (
            AccountDeactivation.objects.select_for_update()
            .filter(id=deactivation_id, user_id=user_id)
            .first()
        )
        if not obj:
            raise APIError("deactivation not found", code=40402, status_code=404)

        if obj.state in (
            AccountDeactivation.DeactivationState.DEACTIVATED,
            AccountDeactivation.DeactivationState.CANCELLED,
        ):
            return {"deactivation_id": obj.id, "state": obj.state, "noop": True}

        obj.state = AccountDeactivation.DeactivationState.CANCELLED
        obj.cancelled_at = timezone.now()
        obj.save(update_fields=["state", "cancelled_at"])
        AccountDeactivationAudit.objects.create(
            deactivation=obj,
            action=AccountDeactivationAudit.AuditAction.CANCELLED,
            request_id=request_id or "",
            details={"reason": reason or "", "by_user_id": user_id},
        )
        return {"deactivation_id": obj.id, "state": obj.state, "noop": False}
