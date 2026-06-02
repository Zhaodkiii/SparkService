import hashlib
import os
import random
import uuid
import logging

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from common.exceptions import APIError
from accounts.infrastructure.email_provider import EmailProvider
from accounts.infrastructure.sms_provider import AliyunSMSProvider
from accounts.models import EmailOTP, LoginAudit, PhoneOTP, SocialIdentity
from accounts.services.phone_number_service import PhoneNumberService
from accounts.services.device_linking_service import DeviceLinkingService
from accounts.services.device_session_service import DeviceSessionService
from ai_config.services import TrialService

flow_logger = logging.getLogger("accounts.flow")


class OTPService:
    OTP_EXPIRATION_MINUTES = int(os.getenv("OTP_EXPIRATION_MINUTES", "5"))
    MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
    LOCKOUT_MINUTES = int(os.getenv("OTP_LOCKOUT_MINUTES", "10"))
    REQUEST_COOLDOWN_SECONDS = int(os.getenv("OTP_REQUEST_COOLDOWN_SECONDS", "30"))
    SMS_DEV_FALLBACK_REASONS = {
        "aliyun_sms_sdk_missing",
        "aliyun_sms_template_not_configured",
        "aliyun_sms_client_unavailable",
    }

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
    def _normalized_whitelist_phones() -> set[str]:
        out: set[str] = set()
        for value in getattr(settings, "OTP_WHITELIST_PHONES", []) or []:
            try:
                out.add(PhoneNumberService.normalize_e164(value))
            except APIError:
                continue
        return out

    @staticmethod
    def _build_phone_username(phone_number: str) -> str:
        User = get_user_model()
        digits = "".join(ch for ch in phone_number if ch.isdigit())
        username_base = f"phone_{digits[-11:] or digits or uuid.uuid4().hex[:8]}"
        username = username_base
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f"{username_base}_{suffix}"
        return username

    @staticmethod
    def request_phone_otp(*, phone_number: str, provider_uid: str, bundle_id: str, device_id: str, ip_address: str, request_id: str):
        flow_logger.info(
            "auth.phone_otp.request.service.begin",
            extra={"action": "auth.phone_otp.request.service", "request_id": request_id, "bundle_id": bundle_id, "device_id": device_id},
        )
        now = timezone.now()
        normalized_phone = PhoneNumberService.normalize_e164(phone_number)

        recent = (
            PhoneOTP.objects.filter(
                phone_number=normalized_phone,
                device_id=device_id or "",
                used_at__isnull=True,
                expires_at__gt=now,
            )
            .order_by("-created_at")
            .first()
        )
        if recent and (now - recent.created_at).total_seconds() < OTPService.REQUEST_COOLDOWN_SECONDS:
            flow_logger.warning(
                "auth.phone_otp.request.service.failed",
                extra={"action": "auth.phone_otp.request.service", "request_id": request_id, "reason": "otp_requested_too_frequently"},
            )
            raise APIError("OTP requested too frequently", code=42901, status_code=429)

        otp_id = str(uuid.uuid4())
        is_whitelisted = normalized_phone in OTPService._normalized_whitelist_phones()
        fixed_code = (getattr(settings, "OTP_FIXED_WHITELIST_CODE", "989898") or "989898").strip() or "989898"
        code = fixed_code if is_whitelisted else f"{random.randint(0, 999999):06d}"
        code_hash = OTPService._hash_code(code)
        expires_at = now + timedelta(minutes=OTPService.OTP_EXPIRATION_MINUTES)

        PhoneOTP.objects.create(
            otp_id=otp_id,
            phone_number=normalized_phone,
            code_hash=code_hash,
            expires_at=expires_at,
            provider_uid=provider_uid or "",
            bundle_id=bundle_id or "",
            device_id=device_id or "",
            ip_address=ip_address or "",
            request_id=request_id or "",
        )

        if is_whitelisted:
            flow_logger.info(
                "auth.phone_otp.request.service.whitelist_hit",
                extra={"action": "auth.phone_otp.request.service", "request_id": request_id, "otp_id": otp_id, "phone_number": normalized_phone},
            )
            return {"otp_id": otp_id, "expires_in": int((expires_at - now).total_seconds())}

        ok, reason, provider_message_id = AliyunSMSProvider.send_login_code(
            phone_number=normalized_phone,
            code=code,
        )
        if not ok:
            if reason in OTPService.SMS_DEV_FALLBACK_REASONS:
                flow_logger.warning(
                    "auth.phone_otp.request.service.sms_dev_fallback",
                    extra={
                        "action": "auth.phone_otp.request.service",
                        "request_id": request_id,
                        "otp_id": otp_id,
                        "phone_number": normalized_phone,
                        "reason": reason,
                    },
                )
            else:
                flow_logger.warning(
                    "auth.phone_otp.request.service.failed",
                    extra={
                        "action": "auth.phone_otp.request.service",
                        "request_id": request_id,
                        "otp_id": otp_id,
                        "phone_number": normalized_phone,
                        "reason": reason,
                        "provider_message_id": provider_message_id,
                    },
                )
                raise APIError("sms_send_failed", code=50231, status_code=502, details={"reason": reason})

        flow_logger.info(
            "auth.phone_otp.request.service.success",
            extra={"action": "auth.phone_otp.request.service", "request_id": request_id, "otp_id": otp_id, "phone_number": normalized_phone},
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
            flow_logger.info(
                "user.register.success",
                extra={
                    "action": "user.register",
                    "request_id": request_id,
                    "channel": "email_otp",
                    "user_id": user.id,
                },
            )

        DeviceLinkingService.try_attach_user_to_trusted_device(
            user=user,
            device_id=device_id,
            bundle_id=bundle_id,
            request_id=request_id,
        )
        try:
            TrialService.try_grant_auto_trial_for_login_device(
                user=user,
                bundle_id=bundle_id or "",
                device_id=device_id or "",
                request_id=request_id,
            )
        except Exception as exc:  # noqa: BLE001 - defensive
            flow_logger.warning("auth.trial.auto_grant.skipped", extra={"action": "auth.trial.auto_grant", "request_id": request_id, "user_id": user.id, "reason": str(exc)})

        token_payload = DeviceSessionService.activate_and_issue_tokens(
            user=user,
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
        )

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

        is_pro = TrialService.is_pro_user(user=user)
        flow_logger.info(
            "auth.otp.verify.service.success",
            extra={
                "action": "auth.otp.verify.service",
                "request_id": request_id,
                "otp_id": otp_id,
                "user_id": user.id,
                "is_pro": is_pro,
            },
        )
        return {
            **token_payload,
            "otp_id": otp.otp_id,
            "is_pro": is_pro,
        }

    @staticmethod
    @transaction.atomic
    def verify_phone_otp_and_issue_tokens(*, otp_id: str, phone_number: str, code: str, request_id: str, ip_address: str, user_agent: str, bundle_id: str, device_id: str):
        normalized_bundle_id = (bundle_id or "").strip()
        flow_logger.info(
            "auth.phone_otp.verify.service.begin",
            extra={"action": "auth.phone_otp.verify.service", "request_id": request_id, "otp_id": otp_id, "bundle_id": normalized_bundle_id, "device_id": device_id},
        )
        now = timezone.now()
        normalized_phone = PhoneNumberService.normalize_e164(phone_number)
        otp = (
            PhoneOTP.objects.select_for_update()
            .filter(otp_id=otp_id, phone_number=normalized_phone)
            .first()
        )
        if not otp:
            flow_logger.warning(
                "auth.phone_otp.verify.service.failed",
                extra={"action": "auth.phone_otp.verify.service", "request_id": request_id, "otp_id": otp_id, "reason": "otp_not_found"},
            )
            raise APIError("OTP not found", code=40411, status_code=404)

        if otp.used_at is not None:
            raise APIError("OTP already used", code=40041, status_code=400)
        if otp.expires_at <= now:
            raise APIError("OTP expired", code=40042, status_code=400)
        if otp.locked_until and otp.locked_until > now:
            raise APIError("OTP temporarily locked", code=42311, status_code=423)
        if otp.bundle_id and normalized_bundle_id and otp.bundle_id != normalized_bundle_id:
            raise APIError("bundle_id mismatch", code=40044, status_code=400)
        normalized_bundle_id = normalized_bundle_id or otp.bundle_id or ""

        expected_hash = OTPService._hash_code(code)
        if expected_hash != otp.code_hash:
            otp.attempts += 1
            if otp.attempts >= OTPService.MAX_ATTEMPTS:
                otp.locked_until = now + timedelta(minutes=OTPService.LOCKOUT_MINUTES)
            otp.save(update_fields=["attempts", "locked_until"])
            LoginAudit.objects.create(
                user=None,
                provider=LoginAudit.LoginProvider.PHONE_OTP,
                outcome=LoginAudit.LoginOutcome.FAILED,
                ip_address=ip_address or "",
                user_agent=user_agent or "",
                bundle_id=normalized_bundle_id,
                device_id=device_id or "",
                raw_claims={"phone_number": normalized_phone},
                request_id=request_id or "",
            )
            raise APIError("Invalid OTP", code=40043, status_code=400)

        otp.used_at = now
        otp.save(update_fields=["used_at"])

        User = get_user_model()
        created_user = False

        identity = (
            SocialIdentity.objects.select_for_update()
            .select_related("user")
            .filter(
                bundle_id=normalized_bundle_id,
                provider=SocialIdentity.Provider.PHONE,
                provider_uid=normalized_phone,
            )
            .first()
        )
        user = identity.user if identity else None

        if user and not user.is_active:
            raise APIError("user_inactive", code=40103, status_code=401)

        def _create_phone_user():
            nonlocal created_user
            created_user = True
            new_user = User.objects.create(
                username=OTPService._build_phone_username(normalized_phone),
                email="",
                is_active=True,
            )
            new_user.set_unusable_password()
            new_user.save(update_fields=["password", "is_active"])
            return new_user

        if identity is None:
            identity, _ = SocialIdentity.objects.get_or_create(
                bundle_id=normalized_bundle_id,
                provider=SocialIdentity.Provider.PHONE,
                provider_uid=normalized_phone,
                defaults={"user": _create_phone_user},
            )
            user = identity.user

        if not user.is_active:
            raise APIError("user_inactive", code=40103, status_code=401)

        DeviceLinkingService.try_attach_user_to_trusted_device(
            user=user,
            device_id=device_id,
            bundle_id=normalized_bundle_id,
            request_id=request_id,
        )
        try:
            TrialService.try_grant_auto_trial_for_login_device(
                user=user,
                bundle_id=normalized_bundle_id,
                device_id=device_id or "",
                request_id=request_id,
            )
        except Exception as exc:  # noqa: BLE001 - defensive
            flow_logger.warning("auth.trial.auto_grant.skipped", extra={"action": "auth.trial.auto_grant", "request_id": request_id, "user_id": user.id, "reason": str(exc)})

        token_payload = DeviceSessionService.activate_and_issue_tokens(
            user=user,
            bundle_id=normalized_bundle_id,
            device_id=device_id,
            request_id=request_id,
        )

        LoginAudit.objects.create(
            user=user,
            provider=LoginAudit.LoginProvider.PHONE_OTP,
            outcome=LoginAudit.LoginOutcome.SUCCESS,
            ip_address=ip_address or "",
            user_agent=user_agent or "",
            bundle_id=normalized_bundle_id,
            device_id=device_id or "",
            raw_claims={"phone_number": normalized_phone},
            request_id=request_id or "",
        )

        is_pro = TrialService.is_pro_user(user=user)
        flow_logger.info(
            "auth.phone_otp.verify.service.success",
            extra={
                "action": "auth.phone_otp.verify.service",
                "request_id": request_id,
                "otp_id": otp_id,
                "user_id": user.id,
                "is_pro": is_pro,
            },
        )
        return {
            "phone_number": normalized_phone,
            "display_name": PhoneNumberService.masked_display(normalized_phone),
            "is_pro": is_pro,
            "is_new_user": created_user,
            "otp_id": otp.otp_id,
            **token_payload,
        }
