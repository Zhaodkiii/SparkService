import time
import hashlib
import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction
from django.db.utils import IntegrityError, OperationalError, ProgrammingError
from common.exceptions import APIError
from accounts.models import LoginAudit, SocialIdentity
from accounts.services.access_control_service import AccessControlService
from accounts.services.login_audit_service import LoginAuditService
from accounts.services.apple_identity_service import AppleIdentityService
from accounts.services.deactivation_service import DeactivationService
from accounts.services.device_linking_service import DeviceLinkingService
from accounts.services.device_session_service import DeviceSessionService
from accounts.services.identity_scope_service import IdentityScopeService
from accounts.services.phone_number_service import PhoneNumberService
from ai_config.services import TrialService

flow_logger = logging.getLogger("accounts.flow")


class LoginService:
    @staticmethod
    def _try_grant_auto_trial(*, user, bundle_id: str, device_id: str, request_id: str):
        # 登录自动试用仅对 settings.AI_TRIAL_AUTO_GRANT_COUNTRY_CODES 内国家生效；失败/跳过不影响登录。
        TrialService.try_grant_auto_trial_for_login_device(
            user=user,
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
        )

    @staticmethod
    def _prepare_login_entitlements(*, user, bundle_id: str, device_id: str, request_id: str) -> None:
        """
        登录侧效应：先关联可信设备（供 country_code 判断），再尝试自动发放 Pro。
        必须在计算响应 is_pro 与返回 token 之前完成（APP-STARTUP-000003）。
        """
        DeviceLinkingService.try_attach_user_to_trusted_device(
            user=user,
            device_id=device_id,
            bundle_id=bundle_id,
            request_id=request_id,
        )
        LoginService._try_grant_auto_trial(
            user=user,
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
        )

    @staticmethod
    def _apply_is_pro(*, user, payload: dict[str, Any]) -> dict[str, Any]:
        """在设备关联与自动发放完成后写入最终 is_pro。"""
        payload["is_pro"] = TrialService.is_pro_user(user=user)
        return payload

    @staticmethod
    def _load_apple_identity_for_update(*, bundle_id: str, subject: str, request_id: str):
        """
        读取 Apple 社交身份绑定；若表未迁移或不可用，抛出可观测的 APIError，避免客户端收到裸 500。
        """
        try:
            return (
                SocialIdentity.objects.select_for_update()
                .select_related("user")
                .filter(
                    bundle_id=bundle_id,
                    provider=SocialIdentity.Provider.APPLE,
                    provider_uid=subject,
                )
                .first()
            )
        except (OperationalError, ProgrammingError) as exc:
            flow_logger.error(
                "auth.apple.identity.store.unavailable",
                extra={
                    "action": "auth.apple.authenticate",
                    "request_id": request_id,
                    "reason": str(exc),
                    "error_code": "apple_identity_store_unavailable",
                },
            )
            raise APIError(
                "apple_identity_store_unavailable",
                code=50323,
                status_code=503,
                details={
                    "reason": "social_identity_table_missing_or_unavailable",
                    "hint": "run `python manage.py migrate accounts`",
                },
            ) from exc

    @staticmethod
    def _find_user_by_identifier(identifier: str, *, bundle_id: str = ""):
        User = get_user_model()
        identifier = identifier.strip()
        normalized_bundle_id = (bundle_id or "").strip()
        identity_scope = IdentityScopeService.resolve(normalized_bundle_id)

        # email
        if "@" in identifier:
            return User.objects.filter(email__iexact=identifier).first()

        # phone
        if identifier.startswith(("+", "00")) or (identifier.isdigit() and len(identifier) >= 7):
            try:
                normalized_phone = PhoneNumberService.normalize_e164(identifier)
            except APIError:
                normalized_phone = ""
            if normalized_phone:
                queryset = SocialIdentity.objects.select_related("user").filter(
                    provider=SocialIdentity.Provider.PHONE,
                    provider_uid=normalized_phone,
                )
                if identity_scope:
                    queryset = queryset.filter(bundle_id=identity_scope)
                identity = queryset.first()
                if identity:
                    return identity.user

        # username
        return User.objects.filter(username__iexact=identifier).first()

    @staticmethod
    def _normalize_apple_full_name(full_name: str) -> str:
        return (full_name or "").strip()

    @staticmethod
    def _resolve_user_display_name(*, user, fallback_email: str = "") -> str:
        name = (getattr(user, "first_name", None) or "").strip()
        if name:
            return name
        email = (getattr(user, "email", None) or fallback_email or "").strip()
        if email:
            if "@" in email:
                prefix = email.split("@", 1)[0].strip()
                return prefix or email
            return email
        return "Apple User"

    @staticmethod
    def _maybe_backfill_apple_first_name(*, user, full_name: str) -> bool:
        normalized = LoginService._normalize_apple_full_name(full_name)
        if not normalized:
            return False
        current = (getattr(user, "first_name", None) or "").strip()
        if current:
            return False
        user.first_name = normalized
        user.save(update_fields=["first_name"])
        return True

    @staticmethod
    def _audit_client_full_name(full_name: str) -> dict[str, Any]:
        normalized = LoginService._normalize_apple_full_name(full_name)
        payload: dict[str, Any] = {"client_full_name_present": bool(normalized)}
        if normalized:
            payload["client_full_name"] = normalized[:64]
        return payload

    @staticmethod
    def _create_apple_user(*, subject: str, chosen_email: str, full_name: str):
        User = get_user_model()
        username_base = f"apple_{subject[:16]}"
        username = username_base
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f"{username_base}_{suffix}"

        user = User.objects.create(username=username, email=chosen_email, is_active=True)
        user.set_unusable_password()
        update_fields = ["password", "is_active"]
        normalized_name = LoginService._normalize_apple_full_name(full_name)
        if normalized_name:
            user.first_name = normalized_name
            update_fields.append("first_name")
        user.save(update_fields=update_fields)
        return user

    @staticmethod
    def authenticate_and_issue_tokens(
        *,
        identifier: str,
        password: str,
        ip_address: str,
        user_agent: str,
        bundle_id: str,
        device_id: str,
        request_id: str,
        provider: str = "password",
    ):
        flow_logger.info(
            "密码登录鉴权开始",
            extra={"action": "auth.password.authenticate", "request_id": request_id, "provider": provider},
        )
        parsed = AccessControlService.parse_identifier_for_deny(identifier)
        AccessControlService.check(
            email=parsed.get("email", ""),
            phone=parsed.get("phone", ""),
            provider=provider,
            bundle_id=bundle_id or "",
            device_id=device_id or "",
            request_id=request_id or "",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        User = get_user_model()
        user = LoginService._find_user_by_identifier(identifier, bundle_id=bundle_id)
        if user is not None:
            AccessControlService.check(
                user_id=user.id,
                email=user.email or "",
                provider=provider,
                bundle_id=bundle_id or "",
                device_id=device_id or "",
                request_id=request_id or "",
                ip_address=ip_address,
                user_agent=user_agent,
            )

        if not user or not user.check_password(password):
            LoginAuditService.write_failure(
                provider=provider,
                bundle_id=bundle_id or "",
                device_id=device_id or "",
                request_id=request_id or "",
                ip_address=ip_address,
                user_agent=user_agent,
                status_code=401,
                error_code=40101,
                error_message="Invalid credentials",
            )
            flow_logger.warning(
                "密码登录鉴权失败",
                extra={
                    "action": "auth.password.authenticate",
                    "outcome": "failed",
                    "request_id": request_id,
                    "provider": provider,
                    "reason": "invalid_credentials",
                },
            )
            raise APIError("Invalid credentials", code=40101, status_code=401)

        if not user.is_active:
            flow_logger.warning(
                "密码登录鉴权失败：用户已停用",
                extra={
                    "action": "auth.password.authenticate",
                    "outcome": "failed",
                    "request_id": request_id,
                    "provider": provider,
                    "reason": "user_inactive",
                    "user_id": user.id,
                },
            )
            raise APIError("user_inactive", code=40103, status_code=401)

        cancel_result = DeactivationService.cancel_pending_on_login(user=user, request_id=request_id)

        LoginAuditService.write_success(
            user=user,
            provider=provider,
            bundle_id=bundle_id or "",
            device_id=device_id or "",
            request_id=request_id or "",
            ip_address=ip_address,
            user_agent=user_agent,
        )

        LoginService._prepare_login_entitlements(
            user=user,
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
        )
        tokens = LoginService._apply_is_pro(
            user=user,
            payload=LoginService._issue_tokens(
                user,
                bundle_id=bundle_id,
                device_id=device_id,
                request_id=request_id,
            ),
        )
        flow_logger.info(
            "密码登录鉴权成功",
            extra={
                "action": "auth.password.authenticate",
                "outcome": "success",
                "request_id": request_id,
                "provider": provider,
                "user_id": user.id,
                "is_pro": tokens.get("is_pro"),
            },
        )
        tokens["deactivation_cancelled"] = cancel_result
        return tokens

    @staticmethod
    @transaction.atomic
    def authenticate_apple_and_issue_tokens(
        *,
        identity_token: str,
        bundle_id: str,
        nonce: str,
        user_identifier: str,
        email: str,
        full_name: str,
        ip_address: str,
        user_agent: str,
        device_id: str,
        request_id: str,
        device_secret: str = "",
    ) -> dict[str, Any]:
        from accounts.services.account_login_resolution_service import AccountLoginResolutionService

        flow_logger.info(
            "Apple 登录鉴权开始",
            extra={"action": "auth.apple.authenticate", "request_id": request_id, "provider": "apple"},
        )
        normalized_bundle_id = (bundle_id or "").strip()
        if not normalized_bundle_id:
            flow_logger.warning(
                "Apple 登录鉴权失败：缺少 bundle_id",
                extra={"action": "auth.apple.authenticate", "request_id": request_id, "reason": "bundle_id_required"},
            )
            raise APIError("bundle_id required", code=40023, status_code=400)
        allowed_bundle_ids = getattr(settings, "APPLE_ALLOWED_BUNDLE_IDS", [])
        if allowed_bundle_ids and normalized_bundle_id not in allowed_bundle_ids:
            flow_logger.warning(
                "Apple 登录鉴权失败：bundle_id 不在允许列表",
                extra={
                    "action": "auth.apple.authenticate",
                    "request_id": request_id,
                    "reason": "bundle_id_not_allowed",
                    "bundle_id": normalized_bundle_id,
                },
            )
            raise APIError("bundle_id_not_allowed", code=40321, status_code=403)

        payload, matched_audience = AppleIdentityService.verify_identity_token(
            identity_token=identity_token,
            audiences=[normalized_bundle_id],
        )
        subject = payload.get("sub")
        if not subject:
            flow_logger.warning(
                "Apple 登录鉴权失败：identity_token 缺少 sub",
                extra={"action": "auth.apple.authenticate", "request_id": request_id, "reason": "apple_sub_missing"},
            )
            raise APIError("apple_sub_missing", code=40123, status_code=401)
        token_nonce = payload.get("nonce")
        if nonce and token_nonce:
            expected_nonce = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
            if token_nonce != expected_nonce:
                flow_logger.warning(
                    "Apple 登录鉴权失败：nonce 校验不通过",
                    extra={"action": "auth.apple.authenticate", "request_id": request_id, "reason": "apple_nonce_mismatch"},
                )
                raise APIError("apple_nonce_mismatch", code=40124, status_code=401)

        identity_scope = IdentityScopeService.resolve(matched_audience)
        email_from_token = (payload.get("email") or "").strip().lower()
        email_from_client = (email or "").strip().lower()
        chosen_email = email_from_token or email_from_client or f"apple_{subject[:12]}@privaterelay.appleid.com"
        email_verified = payload.get("email_verified") in (True, "true", "1")

        AccessControlService.check(
            email=chosen_email if "@" in chosen_email else "",
            provider=LoginAudit.LoginProvider.APPLE,
            bundle_id=normalized_bundle_id,
            device_id=device_id or "",
            request_id=request_id or "",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        existing_apple = (
            SocialIdentity.objects.select_related("user")
            .filter(
                bundle_id=identity_scope,
                provider=SocialIdentity.Provider.APPLE,
                provider_uid=subject,
            )
            .first()
        )
        if existing_apple is not None and existing_apple.user_id:
            AccessControlService.check(
                user_id=existing_apple.user_id,
                email=existing_apple.user.email or chosen_email,
                provider=LoginAudit.LoginProvider.APPLE,
                bundle_id=normalized_bundle_id,
                device_id=device_id or "",
                request_id=request_id or "",
                ip_address=ip_address,
                user_agent=user_agent,
            )

        def _create_user():
            return LoginService._create_apple_user(
                subject=subject,
                chosen_email=chosen_email,
                full_name=full_name,
            )

        def _on_existing(user):
            if email_verified and email_from_token and not (user.email or "").strip():
                user.email = email_from_token
                user.save(update_fields=["email"])
            LoginService._maybe_backfill_apple_first_name(user=user, full_name=full_name)

        result = AccountLoginResolutionService.resolve_verified_identity(
            provider=SocialIdentity.Provider.APPLE,
            normalized_provider_uid=subject,
            real_bundle_id=matched_audience,
            identity_scope=identity_scope,
            device_id=device_id or "",
            device_secret=device_secret or "",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            verified_claims={
                "sub": subject,
                "aud": payload.get("aud"),
                "email": email_from_token,
                "email_verified": payload.get("email_verified"),
                "apple_user_identifier": user_identifier or "",
                **LoginService._audit_client_full_name(full_name),
            },
            create_user=_create_user,
            on_existing_user=_on_existing,
            login_audit_provider=LoginAudit.LoginProvider.APPLE,
        )
        User = get_user_model()
        user = User.objects.filter(id=result["user_id"]).first()
        if user is not None:
            _on_existing(user)
            result["email"] = user.email or ""
            result["display_name"] = LoginService._resolve_user_display_name(
                user=user,
                fallback_email=user.email or chosen_email,
            )
        else:
            result["email"] = chosen_email
            result["display_name"] = LoginService._normalize_apple_full_name(full_name) or "Apple User"

        flow_logger.info(
            "Apple 登录鉴权成功并签发令牌",
            extra={
                "action": "auth.apple.authenticate",
                "outcome": "success",
                "request_id": request_id,
                "user_id": result.get("user_id"),
                "is_new_user": result.get("is_new_user"),
                "account_resolution": result.get("account_resolution"),
                "bundle_id": matched_audience,
                "is_pro": result.get("is_pro"),
            },
        )
        return result

    @staticmethod
    def _issue_tokens(user, *, bundle_id: str, device_id: str, request_id: str = "") -> dict[str, Any]:
        if not getattr(user, "is_active", False):
            raise APIError("user_inactive", code=40103, status_code=401)
        bundle_id = (bundle_id or "").strip()
        device_id = (device_id or "").strip()
        if not bundle_id or not device_id:
            raise APIError("bundle_id and device_id are required", code=40024, status_code=400)
        return DeviceSessionService.activate_and_issue_tokens(
            user=user,
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
        )

    @staticmethod
    def build_current_session(*, user) -> dict[str, Any]:
        """Return latest account session fields for cold-start refresh (no tokens)."""
        if not getattr(user, "is_active", False):
            raise APIError("user_inactive", code=40103, status_code=401)

        providers = set(
            SocialIdentity.objects.filter(user=user).values_list("provider", flat=True)
        )
        formal = {
            SocialIdentity.Provider.APPLE,
            SocialIdentity.Provider.GOOGLE,
            SocialIdentity.Provider.PHONE,
            SocialIdentity.Provider.EMAIL,
        }
        is_device_account = bool(providers) and providers.isdisjoint(formal) and (
            SocialIdentity.Provider.DEVICE in providers
        )

        # 冷启动：优先正式身份，其次 device；不再默认回退 apple。
        if SocialIdentity.Provider.APPLE in providers:
            sign_in_method = "apple"
        elif SocialIdentity.Provider.PHONE in providers:
            sign_in_method = "phone"
        elif SocialIdentity.Provider.EMAIL in providers:
            sign_in_method = "email"
        elif SocialIdentity.Provider.GOOGLE in providers:
            sign_in_method = "google"
        elif SocialIdentity.Provider.DEVICE in providers:
            sign_in_method = "device"
        else:
            sign_in_method = "apple"

        return {
            "user_id": user.id,
            "email": user.email or "",
            "display_name": LoginService._resolve_user_display_name(user=user),
            "is_pro": TrialService.is_pro_user(user=user),
            "is_new_user": False,
            "sign_in_method": sign_in_method,
            "is_device_account": is_device_account,
        }
