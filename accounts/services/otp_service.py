import hashlib
import random
import os
import uuid
import logging

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from common.exceptions import APIError
from accounts.infrastructure.email_provider import EmailProvider
from accounts.models import AccountProfile, EmailOTP, LoginAudit

flow_logger = logging.getLogger("accounts.flow")


class OTPService:
    OTP_EXPIRATION_MINUTES = int(os.getenv("OTP_EXPIRATION_MINUTES", "5"))
    MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
    LOCKOUT_MINUTES = int(os.getenv("OTP_LOCKOUT_MINUTES", "10"))
    REQUEST_COOLDOWN_SECONDS = int(os.getenv("OTP_REQUEST_COOLDOWN_SECONDS", "30"))

    @staticmethod
    def _hash_code(code: str) -> str:
        # Use a simple hash; for real systems use per-tenant salt and strong KDF.
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    @staticmethod
    def request_email_otp(*, email: str, provider_uid: str, bundle_id: str, device_id: str, ip_address: str, request_id: str):
        flow_logger.info(
            "auth.otp.request.service.begin",
            extra={"action": "auth.otp.request.service", "request_id": request_id, "bundle_id": bundle_id, "device_id": device_id},
        )
        now = timezone.now()
        email = email.strip().lower()

        # Cooldown check for same dimension.
        recent = (
            EmailOTP.objects.filter(
                email=email,
                device_id=device_id or "",
                used_at__isnull=True,
                expires_at__gt=now,
            )
            .order_by("-created_at")
            .first()
        )
        if recent and (now - recent.created_at).total_seconds() < OTPService.REQUEST_COOLDOWN_SECONDS:
            flow_logger.warning(
                "auth.otp.request.service.failed",
                extra={"action": "auth.otp.request.service", "request_id": request_id, "reason": "otp_requested_too_frequently"},
            )
            raise APIError("OTP requested too frequently", code=42901, status_code=429)

        otp_id = str(uuid.uuid4())
        code = f"{random.randint(0, 999999):06d}"
        code_hash = OTPService._hash_code(code)
        expires_at = now + timedelta(minutes=OTPService.OTP_EXPIRATION_MINUTES)

        # Persist before sending to avoid race conditions.
        EmailOTP.objects.create(
            otp_id=otp_id,
            email=email,
            code_hash=code_hash,
            expires_at=expires_at,
            provider_uid=provider_uid or "",
            bundle_id=bundle_id or "",
            device_id=device_id or "",
            ip_address=ip_address or "",
            request_id=request_id or "",
        )

        EmailProvider.send_otp(email=email, code=code, request_id=request_id or "", provider_uid=provider_uid or "")
        flow_logger.info(
            "auth.otp.request.service.success",
            extra={"action": "auth.otp.request.service", "request_id": request_id, "otp_id": otp_id},
        )
        return {"otp_id": otp_id, "expires_in": int((expires_at - now).total_seconds())}

    @staticmethod
    @transaction.atomic
    def verify_email_otp_and_issue_tokens(*, otp_id: str, email: str, code: str, request_id: str, ip_address: str, user_agent: str, bundle_id: str, device_id: str):
        flow_logger.info(
            "auth.otp.verify.service.begin",
            extra={"action": "auth.otp.verify.service", "request_id": request_id, "otp_id": otp_id, "bundle_id": bundle_id, "device_id": device_id},
        )
        now = timezone.now()
        email = email.strip().lower()
        otp = (
            EmailOTP.objects.select_for_update()
            .filter(otp_id=otp_id, email=email)
            .first()
        )
        if not otp:
            flow_logger.warning(
                "auth.otp.verify.service.failed",
                extra={"action": "auth.otp.verify.service", "request_id": request_id, "otp_id": otp_id, "reason": "otp_not_found"},
            )
            raise APIError("OTP not found", code=40401, status_code=404)

        if otp.used_at is not None:
            flow_logger.warning(
                "auth.otp.verify.service.failed",
                extra={"action": "auth.otp.verify.service", "request_id": request_id, "otp_id": otp_id, "reason": "otp_already_used"},
            )
            raise APIError("OTP already used", code=40011, status_code=400)
        if otp.expires_at <= now:
            flow_logger.warning(
                "auth.otp.verify.service.failed",
                extra={"action": "auth.otp.verify.service", "request_id": request_id, "otp_id": otp_id, "reason": "otp_expired"},
            )
            raise APIError("OTP expired", code=40012, status_code=400)
        if otp.locked_until and otp.locked_until > now:
            flow_logger.warning(
                "auth.otp.verify.service.failed",
                extra={"action": "auth.otp.verify.service", "request_id": request_id, "otp_id": otp_id, "reason": "otp_temporarily_locked"},
            )
            raise APIError("OTP temporarily locked", code=42301, status_code=423)

        expected_hash = OTPService._hash_code(code)
        if expected_hash != otp.code_hash:
            otp.attempts += 1
            if otp.attempts >= OTPService.MAX_ATTEMPTS:
                otp.locked_until = now + timedelta(minutes=OTPService.LOCKOUT_MINUTES)
            otp.save(update_fields=["attempts", "locked_until"])
            LoginAudit.objects.create(
                user=None,
                provider=LoginAudit.LoginProvider.EMAIL_OTP,
                outcome=LoginAudit.LoginOutcome.FAILED,
                ip_address=ip_address or "",
                user_agent=user_agent or "",
                bundle_id=bundle_id or "",
                device_id=device_id or "",
                raw_claims=None,
                request_id=request_id or "",
            )
            flow_logger.warning(
                "auth.otp.verify.service.failed",
                extra={"action": "auth.otp.verify.service", "request_id": request_id, "otp_id": otp_id, "reason": "invalid_otp"},
            )
            raise APIError("Invalid OTP", code=40013, status_code=400)

        otp.used_at = now
        otp.save(update_fields=["used_at"])

        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            # Create a user placeholder for OTP-only login.
            flow_logger.info(
                "user.register.begin",
                extra={"action": "user.register", "request_id": request_id, "channel": "email_otp"},
            )
            user = User.objects.create(username=email, email=email)
            user.set_unusable_password()
            user.save(update_fields=["password"])
            AccountProfile.objects.get_or_create(user=user, defaults={"phone_number": ""})
            flow_logger.info(
                "user.register.success",
                extra={
                    "action": "user.register",
                    "request_id": request_id,
                    "channel": "email_otp",
                    "user_id": user.id,
                },
            )

        refresh = RefreshToken.for_user(user)
        access = refresh.access_token
        expires_in = int(access["exp"] - timezone.now().timestamp())

        LoginAudit.objects.create(
            user=user,
            provider=LoginAudit.LoginProvider.EMAIL_OTP,
            outcome=LoginAudit.LoginOutcome.SUCCESS,
            ip_address=ip_address or "",
            user_agent=user_agent or "",
            bundle_id=bundle_id or "",
            device_id=device_id or "",
            raw_claims=None,
            request_id=request_id or "",
        )

        flow_logger.info(
            "auth.otp.verify.service.success",
            extra={"action": "auth.otp.verify.service", "request_id": request_id, "otp_id": otp_id, "user_id": user.id},
        )
        return {
            "user_id": user.id,
            "access_token": str(access),
            "refresh_token": str(refresh),
            "expires_in": expires_in,
            "token_type": "Bearer",
            "otp_id": otp.otp_id,
        }
