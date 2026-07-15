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
from accounts.models import EmailOTP, LoginAudit, PhoneOTP, SocialIdentity
from accounts.services.identity_scope_service import IdentityScopeService
from accounts.services.phone_number_service import PhoneNumberService
from notification_center.services import NotificationCenterService

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
    def request_email_otp(*, email: str, provider_uid: str, bundle_id: str, device_id: str, ip_address: str, request_id: str, scene: str = "login"):
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
            raise OTPService._otp_request_rate_limited_error()

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

        scene_aliases = {
            "login": "account.auth.login_otp_requested",
            "registration": "account.auth.registration_otp_requested",
            "identity_bind": "account.auth.identity_bind_otp_requested",
            "identity_change": "account.auth.identity_change_otp_requested",
            "identity_reauth": "account.auth.identity_reauth_otp_requested",
            "password_reset": "account.auth.password_reset_otp_requested",
        }
        scene_key = scene_aliases.get((scene or "").strip(), scene or "account.auth.login_otp_requested")
        ok, reason, provider_message_id = NotificationCenterService.send_email_otp(
            email=email,
            code=code,
            request_id=request_id or "",
            provider_uid=provider_uid or "",
            bundle_id=bundle_id or "",
            device_id=device_id or "",
            ip_address=ip_address or "",
            otp_id=otp_id,
            expires_at=expires_at,
            scene=scene_key,
        )
        if not ok:
            flow_logger.warning(
                "auth.otp.request.service.failed",
                extra={
                    "action": "auth.otp.request.service",
                    "request_id": request_id,
                    "otp_id": otp_id,
                    "reason": reason,
                    "provider_message_id": provider_message_id,
                },
            )
            raise APIError("email_send_failed", code=50241, status_code=502, details={"reason": reason})
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
    def _provider_error_payload(reason: str, *, error_type: str) -> tuple[str, dict]:
        raw_reason = (reason or "").strip()
        return error_type, {
            "error_type": error_type,
            "reason": raw_reason or error_type,
        }

    @staticmethod
    def _phone_otp_send_error(reason: str) -> APIError:
        value = (reason or "").strip()
        lowered = value.lower()
        if "business_limit_control" in lowered or value == "otp_rate_limited":
            msg, details = OTPService._provider_error_payload(value, error_type="sms_send_rate_limited")
            return APIError(msg, code=42902, status_code=429, details=details)
        if value in {"sms_send_unknown", "submit_unknown", "otp_rate_limit_unavailable"} or "timeout" in lowered:
            msg, details = OTPService._provider_error_payload(value, error_type="sms_send_unknown")
            return APIError(msg, code=50331, status_code=503, details=details)
        msg, details = OTPService._provider_error_payload(value, error_type="sms_send_failed")
        return APIError(msg, code=50231, status_code=502, details=details)

    @staticmethod
    def _otp_request_rate_limited_error() -> APIError:
        return APIError(
            "otp_requested_too_frequently",
            code=42901,
            status_code=429,
            details={"error_type": "otp_requested_too_frequently", "reason": "otp_requested_too_frequently"},
        )

    @staticmethod
    def _phone_region_not_supported_error(normalized_phone: str) -> APIError:
        region_code, dial_code = PhoneNumberService.resolve_region(normalized_phone)
        return APIError(
            "phone_region_not_supported",
            code=40033,
            status_code=400,
            details={
                "error_type": "phone_region_not_supported",
                "reason": "phone_region_not_supported",
                "phone_region": region_code,
                "dial_code": dial_code,
                "supported_regions": PhoneNumberService._normalized_supported_sms_otp_regions(),
                "supported_dial_codes": PhoneNumberService._normalized_supported_sms_otp_dial_codes(),
            },
        )

    @staticmethod
    def request_phone_otp(*, phone_number: str, provider_uid: str, bundle_id: str, device_id: str, ip_address: str, request_id: str, scene: str = "login", user_id: int | None = None, actor_user_id: int | None = None):
        flow_logger.info(
            "auth.phone_otp.request.service.begin",
            extra={"action": "auth.phone_otp.request.service", "request_id": request_id, "bundle_id": bundle_id, "device_id": device_id},
        )
        now = timezone.now()
        normalized_phone = PhoneNumberService.normalize_e164(phone_number)
        normalized_bundle_id = (bundle_id or "").strip()
        identity_scope = IdentityScopeService.resolve(normalized_bundle_id)
        normalized_device_id = (device_id or "").strip()
        scene_key = NotificationCenterService._normalize_scene_key(scene or "login")
        region_code, dial_code = PhoneNumberService.resolve_region(normalized_phone)

        if not PhoneNumberService.is_supported_sms_otp_region(normalized_phone):
            flow_logger.warning(
                "auth.phone_otp.request.service.failed",
                extra={
                    "action": "auth.phone_otp.request.service",
                    "request_id": request_id,
                    "reason": "phone_region_not_supported",
                    "bundle_id": normalized_bundle_id,
                    "device_id": normalized_device_id,
                    "phone_region": region_code,
                    "dial_code": dial_code,
                    "phone_number": PhoneNumberService.masked_display(normalized_phone),
                },
            )
            raise OTPService._phone_region_not_supported_error(normalized_phone)

        recent = (
            PhoneOTP.objects.filter(
                phone_number=normalized_phone,
                device_id=normalized_device_id,
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
            raise OTPService._otp_request_rate_limited_error()

        otp_id = str(uuid.uuid4())
        is_whitelisted = normalized_phone in OTPService._normalized_whitelist_phones()
        fixed_code = (getattr(settings, "OTP_FIXED_WHITELIST_CODE", "989898") or "989898").strip() or "989898"
        code = fixed_code if is_whitelisted else f"{random.randint(0, 999999):06d}"
        code_hash = OTPService._hash_code(code)
        expires_at = now + timedelta(minutes=OTPService.OTP_EXPIRATION_MINUTES)

        resolved_user = None
        resolved_identity = None
        identity_owned_scenes = {
            "account.lifecycle.deactivation_requested",
            "account.auth.identity_reauth_otp_requested",
            "account.auth.identity_reauth",
            "identity_reauth",
        }
        if scene_key in identity_owned_scenes or (scene or "").strip() in {"identity_reauth", "account_deactivation"}:
            if user_id is None:
                raise APIError("user_id_required_for_account_deactivation", code=40061, status_code=400)
            if actor_user_id is None or int(actor_user_id) != int(user_id):
                raise APIError("user_context_mismatch", code=40361, status_code=403)
            identity = (
                SocialIdentity.objects.select_related("user")
                .filter(
                    bundle_id=identity_scope,
                    provider=SocialIdentity.Provider.PHONE,
                    provider_uid=normalized_phone,
                )
                .first()
            )
            if identity is None or identity.user_id != int(user_id):
                raise APIError("user_identity_mismatch", code=40901, status_code=409)
            if not identity.user.is_active:
                raise APIError("user_inactive", code=40103, status_code=401)
            resolved_identity = identity
            resolved_user = identity.user
        else:
            if user_id:
                flow_logger.warning(
                    "auth.phone_otp.request.user_id_ignored_for_login",
                    extra={
                        "action": "auth.phone_otp.request",
                        "request_id": request_id,
                        "bundle_id": normalized_bundle_id,
                        "user_id": user_id,
                    },
                )
            identity = (
                SocialIdentity.objects.select_related("user")
                .filter(
                    bundle_id=identity_scope,
                    provider=SocialIdentity.Provider.PHONE,
                    provider_uid=normalized_phone,
                )
                .first()
            )
            if identity is not None:
                if not identity.user.is_active:
                    raise APIError("user_inactive", code=40103, status_code=401)
                resolved_identity = identity
                resolved_user = identity.user

        otp = PhoneOTP.objects.create(
            otp_id=otp_id,
            phone_number=normalized_phone,
            code_hash=code_hash,
            expires_at=expires_at,
            provider_uid=provider_uid or "",
            bundle_id=normalized_bundle_id,
            device_id=normalized_device_id,
            ip_address=ip_address or "",
            scene=scene_key,
            requested_user=resolved_user,
            resolved_identity=resolved_identity,
            request_id=request_id or "",
            send_status=PhoneOTP.SendStatus.QUEUED,
        )

        if is_whitelisted:
            PhoneOTP.objects.filter(id=otp.id).update(send_status=PhoneOTP.SendStatus.ACCEPTED)
            flow_logger.info(
                "auth.phone_otp.request.service.whitelist_hit",
                extra={"action": "auth.phone_otp.request.service", "request_id": request_id, "otp_id": otp_id},
            )
            return {"otp_id": otp_id, "expires_in": int((expires_at - now).total_seconds())}

        ok, reason, provider_message_id = NotificationCenterService.send_phone_otp(
            phone_number=normalized_phone,
            code=code,
            request_id=request_id or "",
            provider_uid=provider_uid or "",
            bundle_id=normalized_bundle_id,
            device_id=normalized_device_id,
            ip_address=ip_address or "",
            otp_id=otp_id,
            expires_at=expires_at,
            scene=scene_key,
            user_id=resolved_user.id if resolved_user else None,
            dispatch_sync=True,
        )
        if not ok:
            now_failed = timezone.now()
            update_fields = {
                "send_status": PhoneOTP.SendStatus.SUBMIT_UNKNOWN if "unknown" in (reason or "").lower() else PhoneOTP.SendStatus.SUBMIT_FAILED,
                "send_error_code": (reason or "sms_send_failed")[:128],
                "send_error_message": reason or "sms_send_failed",
                "invalidated_at": now_failed,
            }
            if str(provider_message_id).isdigit():
                update_fields["notification_message_id"] = int(provider_message_id)
            PhoneOTP.objects.filter(id=otp.id).update(**update_fields)
            flow_logger.warning(
                "auth.phone_otp.request.service.failed",
                extra={
                    "action": "auth.phone_otp.request.service",
                    "request_id": request_id,
                    "otp_id": otp_id,
                    "reason": reason,
                    "provider_message_id": provider_message_id,
                },
            )
            raise OTPService._phone_otp_send_error(reason)

        update_fields = {"send_status": PhoneOTP.SendStatus.ACCEPTED, "invalidated_at": None, "send_error_code": "", "send_error_message": ""}
        if str(provider_message_id).isdigit():
            update_fields["notification_message_id"] = int(provider_message_id)
        PhoneOTP.objects.filter(id=otp.id).update(**update_fields)

        flow_logger.info(
            "auth.phone_otp.request.service.success",
            extra={"action": "auth.phone_otp.request.service", "request_id": request_id, "otp_id": otp_id},
        )
        return {"otp_id": otp_id, "expires_in": int((expires_at - now).total_seconds())}

    @staticmethod
    @transaction.atomic
    def verify_email_otp_and_issue_tokens(*, otp_id: str, email: str, code: str, request_id: str, ip_address: str, user_agent: str, bundle_id: str, device_id: str, device_secret: str = ""):
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

        from accounts.services.account_login_resolution_service import AccountLoginResolutionService

        User = get_user_model()
        normalized_bundle_id = (bundle_id or "").strip() or (otp.bundle_id or "")
        identity_scope = IdentityScopeService.resolve(normalized_bundle_id)

        # Legacy：仅在无正式 email identity 且无设备账户可升级时，把 User.email 懒绑定为 SocialIdentity。
        existing_email = (
            SocialIdentity.objects.filter(
                bundle_id=identity_scope,
                provider=SocialIdentity.Provider.EMAIL,
                provider_uid=email,
            )
            .first()
        )
        device_identity = (
            SocialIdentity.objects.filter(
                bundle_id=identity_scope,
                provider=SocialIdentity.Provider.DEVICE,
                provider_uid=(device_id or "").strip(),
            ).first()
            if (device_id or "").strip()
            else None
        )
        if existing_email is None and device_identity is None:
            legacy_user = User.objects.filter(email__iexact=email).first()
            if legacy_user is not None:
                if not legacy_user.is_active:
                    raise APIError("user_inactive", code=40103, status_code=401)
                SocialIdentity.objects.get_or_create(
                    bundle_id=identity_scope,
                    provider=SocialIdentity.Provider.EMAIL,
                    provider_uid=email,
                    defaults={"user": legacy_user},
                )

        def _create_email_user():
            flow_logger.info(
                "user.register.begin",
                extra={"action": "user.register", "request_id": request_id, "channel": "email_otp"},
            )
            new_user = User.objects.create(username=email, email=email)
            new_user.set_unusable_password()
            new_user.save(update_fields=["password"])
            flow_logger.info(
                "user.register.success",
                extra={
                    "action": "user.register",
                    "request_id": request_id,
                    "channel": "email_otp",
                    "user_id": new_user.id,
                    "identity_scope": identity_scope,
                },
            )
            return new_user

        resolved = AccountLoginResolutionService.resolve_verified_identity(
            provider=SocialIdentity.Provider.EMAIL,
            normalized_provider_uid=email,
            real_bundle_id=normalized_bundle_id,
            identity_scope=identity_scope,
            device_id=device_id or "",
            device_secret=device_secret or "",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            verified_claims={"email": email},
            create_user=_create_email_user,
            login_audit_provider=LoginAudit.LoginProvider.EMAIL_OTP,
        )
        flow_logger.info(
            "auth.otp.verify.service.success",
            extra={
                "action": "auth.otp.verify.service",
                "request_id": request_id,
                "otp_id": otp_id,
                "user_id": resolved.get("user_id"),
                "is_pro": resolved.get("is_pro"),
                "identity_scope": identity_scope,
                "is_new_user": resolved.get("is_new_user"),
                "account_resolution": resolved.get("account_resolution"),
            },
        )
        return {
            **resolved,
            "otp_id": otp.otp_id,
            "email": resolved.get("email") or email,
        }

    @staticmethod
    @transaction.atomic
    def verify_phone_otp_and_issue_tokens(*, otp_id: str, phone_number: str, code: str, request_id: str, ip_address: str, user_agent: str, bundle_id: str, device_id: str, device_secret: str = ""):
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
        if otp.invalidated_at is not None:
            raise APIError("OTP unavailable", code=40045, status_code=400)
        if otp.send_status in {PhoneOTP.SendStatus.QUEUED, PhoneOTP.SendStatus.SUBMIT_FAILED, PhoneOTP.SendStatus.SUBMIT_UNKNOWN}:
            raise APIError("OTP SMS not sent", code=40046, status_code=400)
        if otp.locked_until and otp.locked_until > now:
            raise APIError("OTP temporarily locked", code=42311, status_code=423)
        if otp.bundle_id and normalized_bundle_id and otp.bundle_id != normalized_bundle_id:
            raise APIError("bundle_id mismatch", code=40044, status_code=400)
        normalized_bundle_id = normalized_bundle_id or otp.bundle_id or ""
        identity_scope = IdentityScopeService.resolve(normalized_bundle_id)

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

        from accounts.services.account_login_resolution_service import AccountLoginResolutionService

        User = get_user_model()

        def _create_phone_user():
            new_user = User.objects.create(
                username=OTPService._build_phone_username(normalized_phone),
                email="",
                is_active=True,
            )
            new_user.set_unusable_password()
            new_user.save(update_fields=["password", "is_active"])
            return new_user

        resolved = AccountLoginResolutionService.resolve_verified_identity(
            provider=SocialIdentity.Provider.PHONE,
            normalized_provider_uid=normalized_phone,
            real_bundle_id=normalized_bundle_id,
            identity_scope=identity_scope,
            device_id=device_id or "",
            device_secret=device_secret or "",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            verified_claims={"phone_number": normalized_phone},
            create_user=_create_phone_user,
            login_audit_provider=LoginAudit.LoginProvider.PHONE_OTP,
        )
        flow_logger.info(
            "auth.phone_otp.verify.service.success",
            extra={
                "action": "auth.phone_otp.verify.service",
                "request_id": request_id,
                "otp_id": otp_id,
                "user_id": resolved.get("user_id"),
                "is_pro": resolved.get("is_pro"),
                "account_resolution": resolved.get("account_resolution"),
            },
        )
        return {
            **resolved,
            "phone_number": normalized_phone,
            "display_name": resolved.get("display_name")
            or PhoneNumberService.masked_display(normalized_phone),
            "otp_id": otp.otp_id,
        }
