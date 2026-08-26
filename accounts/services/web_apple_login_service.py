"""Web Apple login orchestration (CHAT-WEB-019D).

Issues AccountWebSession-backed tokens for Chat Web. Hard isolation rules:
- Never creates TrustedDevice / AccountDeviceSession.
- Never calls DeviceSessionService (no device attach, no single-device replace).
- Identity resolution shares the SocialIdentity scope with mobile so the same
  Apple subject maps to the same User and therefore the same chat data.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.utils import IntegrityError, OperationalError, ProgrammingError

from accounts.models import LoginAudit, SocialIdentity
from accounts.services.access_control_service import AccessControlService
from accounts.services.deactivation_service import DeactivationService
from accounts.services.identity_scope_service import IdentityScopeService
from accounts.services.login_audit_service import LoginAuditService
from accounts.services.login_service import LoginService
from accounts.services.web_apple_identity_service import WebAppleIdentityService
from accounts.services.web_session_service import WebSessionService
from common.exceptions import APIError

flow_logger = logging.getLogger("accounts.flow")


class WebAppleLoginService:
    @staticmethod
    def _verify_upstream(*, identity_token: str, authorization_code: str, nonce: str, service_id: str, redirect_uri: str) -> dict[str, Any]:
        """All network verification happens before any DB transaction."""
        payload = WebAppleIdentityService.verify_identity_token(
            identity_token=identity_token,
            service_id=service_id,
            nonce=nonce,
        )
        subject = (payload.get("sub") or "").strip()
        if not subject:
            raise APIError("apple_web_token_invalid", code=40172, status_code=401)

        if (authorization_code or "").strip():
            # redirect_uri must hit the HTTPS allowlist before code exchange.
            if not redirect_uri:
                raise APIError("apple_web_callback_invalid", code=40071, status_code=400)
            exchanged = WebAppleIdentityService.exchange_authorization_code(
                authorization_code=authorization_code,
                service_id=service_id,
                redirect_uri=redirect_uri,
            )
            WebAppleIdentityService.verify_code_exchange_subject(
                exchanged_id_token=exchanged.get("id_token", ""),
                expected_subject=subject,
            )
        return payload

    @staticmethod
    def _load_scoped_identity(*, identity_scope: str, subject: str):
        try:
            return (
                SocialIdentity.objects.select_for_update()
                .select_related("user")
                .filter(
                    bundle_id=identity_scope,
                    provider=SocialIdentity.Provider.APPLE,
                    provider_uid=subject,
                )
                .first()
            )
        except (OperationalError, ProgrammingError) as exc:
            flow_logger.error(
                "auth.apple.web.identity.store.unavailable",
                extra={"action": "auth.apple.web.login", "reason": str(exc)},
            )
            raise APIError("web_session_store_unavailable", code=50373, status_code=503) from exc

    @staticmethod
    @transaction.atomic
    def authenticate_apple_web_and_issue_tokens(
        *,
        identity_token: str,
        authorization_code: str,
        nonce: str,
        service_id: str,
        redirect_uri: str,
        ip_address: str = "",
        user_agent: str = "",
        request_id: str = "",
        user_identifier: str = "",
        email: str = "",
        full_name: str = "",
    ) -> dict[str, Any]:
        from ai_config.services import TrialService

        flow_logger.info(
            "Web Apple 登录鉴权开始",
            extra={"action": "auth.apple.web.login", "request_id": request_id, "provider": "apple"},
        )
        if not getattr(settings, "WEB_APPLE_LOGIN_V2_ENABLED", False):
            raise APIError("apple_web_login_disabled", code=50374, status_code=503)

        service_id = WebAppleIdentityService.validate_service_id(service_id)
        if (authorization_code or "").strip() and not (redirect_uri or "").strip():
            raise APIError("apple_web_callback_invalid", code=40071, status_code=400)

        payload = WebAppleLoginService._verify_upstream(
            identity_token=identity_token,
            authorization_code=authorization_code,
            nonce=nonce,
            service_id=service_id,
            redirect_uri=redirect_uri,
        )
        subject = (payload.get("sub") or "").strip()
        identity_scope = IdentityScopeService.resolve(service_id)

        email_from_token = (payload.get("email") or "").strip().lower()
        email_from_client = (email or "").strip().lower()
        chosen_email = email_from_token or email_from_client or f"apple_{subject[:12]}@privaterelay.appleid.com"
        email_verified = payload.get("email_verified") in (True, "true", "1")

        AccessControlService.check(
            email=chosen_email if "@" in chosen_email else "",
            provider=LoginAudit.LoginProvider.APPLE,
            bundle_id=service_id,
            device_id="",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        existing = WebAppleLoginService._load_scoped_identity(identity_scope=identity_scope, subject=subject)
        User = get_user_model()
        created_user = False

        if existing is not None and existing.user_id:
            user = existing.user
            if not user.is_active:
                raise APIError("user_inactive", code=40103, status_code=401)
            if email_verified and email_from_token and not (user.email or "").strip():
                user.email = email_from_token
                user.save(update_fields=["email"])
            LoginService._maybe_backfill_apple_first_name(user=user, full_name=full_name)
            account_resolution = "existing_identity_login"
        else:
            # Never merge by email / Private Relay email alone (6.4 rule 6).
            if email_verified and email_from_token and "@" in email_from_token:
                email_owner = User.objects.filter(email__iexact=email_from_token).first()
                if email_owner is not None:
                    flow_logger.warning(
                        "Web Apple 登录：身份不可安全关联",
                        extra={
                            "action": "auth.apple.web.login",
                            "outcome": "failed",
                            "request_id": request_id,
                            "reason": "apple_web_identity_link_required",
                        },
                    )
                    raise APIError("apple_web_identity_link_required", code=40972, status_code=409)
            user = LoginService._create_apple_user(
                subject=subject,
                chosen_email=chosen_email,
                full_name=full_name,
            )
            try:
                SocialIdentity.objects.create(
                    user=user,
                    bundle_id=identity_scope,
                    provider=SocialIdentity.Provider.APPLE,
                    provider_uid=subject,
                )
                created_user = True
                account_resolution = "formal_account_created"
            except IntegrityError:
                # Concurrent web/mobile login created the identity first: reuse it.
                User.objects.filter(id=user.id).delete()
                existing = WebAppleLoginService._load_scoped_identity(identity_scope=identity_scope, subject=subject)
                if existing is None or not existing.user_id:
                    raise APIError("apple_web_identity_link_required", code=40972, status_code=409) from None
                user = existing.user
                if not user.is_active:
                    raise APIError("user_inactive", code=40103, status_code=401)
                account_resolution = "existing_identity_login"

        AccessControlService.check(
            user_id=user.id,
            email=user.email or chosen_email,
            provider=LoginAudit.LoginProvider.APPLE,
            bundle_id=service_id,
            device_id="",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Web session domain: independent lifecycle, no device attach, no trial grant.
        session = WebSessionService.create_session(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        tokens = WebSessionService.issue_tokens_for_session(user=user, session=session)

        LoginAuditService.write_success(
            user=user,
            provider=LoginAudit.LoginProvider.APPLE,
            bundle_id=service_id,
            device_id="",
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            raw_claims={
                "channel": "web",
                "identity_scope": identity_scope,
                "account_resolution": account_resolution,
                "apple_user_identifier": user_identifier or "",
                "client_full_name_present": bool((full_name or "").strip()),
            },
        )
        cancel_result = DeactivationService.cancel_pending_on_login(user=user, request_id=request_id)

        result = {
            **tokens,
            "email": user.email or chosen_email,
            "display_name": LoginService._resolve_user_display_name(user=user, fallback_email=user.email or chosen_email),
            "is_new_user": created_user,
            "sign_in_method": "apple",
            "session_class": "web",
            "account_resolution": account_resolution,
            "identity_scope": identity_scope,
            "deactivation_cancelled": cancel_result,
            "is_pro": TrialService.is_pro_user(user=user),
        }
        flow_logger.info(
            "Web Apple 登录鉴权成功并签发 Web 令牌",
            extra={
                "action": "auth.apple.web.login",
                "outcome": "success",
                "request_id": request_id,
                "user_id": user.id,
                "is_new_user": created_user,
                "account_resolution": account_resolution,
            },
        )
        return result
