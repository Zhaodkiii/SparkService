import time
import hashlib
import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction
from django.db.utils import IntegrityError, OperationalError, ProgrammingError
from rest_framework_simplejwt.tokens import RefreshToken

from common.exceptions import APIError
from accounts.models import AccountProfile, LoginAudit, SocialIdentity
from accounts.services.apple_identity_service import AppleIdentityService

flow_logger = logging.getLogger("accounts.flow")


class LoginService:
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
    def _find_user_by_identifier(identifier: str):
        User = get_user_model()
        identifier = identifier.strip()

        # email
        if "@" in identifier:
            return User.objects.filter(email__iexact=identifier).first()

        # phone (stored on AccountProfile)
        if identifier.isdigit() and len(identifier) >= 7:
            return (
                User.objects.filter(profile__phone_number=identifier)
                .select_related("profile")
                .first()
            )

        # username
        return User.objects.filter(username__iexact=identifier).first()

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
        User = get_user_model()
        user = LoginService._find_user_by_identifier(identifier)

        if not user or not user.check_password(password):
            LoginAudit.objects.create(
                user=None,
                provider=provider,
                outcome=LoginAudit.LoginOutcome.FAILED,
                ip_address=ip_address,
                user_agent=user_agent,
                bundle_id=bundle_id or "",
                device_id=device_id or "",
                raw_claims=None,
                request_id=request_id or "",
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

        # Ensure profile exists for phone-related flows.
        AccountProfile.objects.get_or_create(user=user, defaults={"phone_number": ""})

        LoginAudit.objects.create(
            user=user,
            provider=provider,
            outcome=LoginAudit.LoginOutcome.SUCCESS,
            ip_address=ip_address,
            user_agent=user_agent,
            bundle_id=bundle_id or "",
            device_id=device_id or "",
            raw_claims=None,
            request_id=request_id or "",
        )

        tokens = LoginService._issue_tokens(user)
        flow_logger.info(
            "密码登录鉴权成功",
            extra={
                "action": "auth.password.authenticate",
                "outcome": "success",
                "request_id": request_id,
                "provider": provider,
                "user_id": user.id,
            },
        )
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
    ) -> dict[str, Any]:
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

        # 关键防线：只使用 Apple 已验签且 aud 匹配后的 bundle_id 作为身份维度。
        identity = LoginService._load_apple_identity_for_update(
            bundle_id=matched_audience,
            subject=subject,
            request_id=request_id,
        )

        email_from_token = (payload.get("email") or "").strip().lower()
        email_from_client = (email or "").strip().lower()
        chosen_email = email_from_token or email_from_client or f"apple_{subject[:12]}@privaterelay.appleid.com"
        chosen_name = (full_name or "").strip() or "Apple User"

        User = get_user_model()
        created_user = False

        if identity:
            user = identity.user
            if email_from_token and user.email.lower() != email_from_token:
                user.email = email_from_token
                user.save(update_fields=["email"])
        else:
            # 首次登录：创建用户并绑定 apple sub；唯一约束保证并发下幂等。
            flow_logger.info(
                "Apple 渠道用户首次注册开始",
                extra={
                    "action": "user.register",
                    "request_id": request_id,
                    "channel": "apple",
                    "bundle_id": matched_audience,
                },
            )
            username_base = f"apple_{subject[:16]}"
            username = username_base
            suffix = 1
            while User.objects.filter(username=username).exists():
                suffix += 1
                username = f"{username_base}_{suffix}"

            user = User.objects.create(username=username, email=chosen_email)
            user.set_unusable_password()
            user.first_name = chosen_name
            user.save(update_fields=["password", "first_name"])
            AccountProfile.objects.get_or_create(user=user, defaults={"phone_number": ""})

            # 并发首登下，唯一约束可能被并发请求同时命中；冲突时回退读取已创建记录。
            try:
                SocialIdentity.objects.create(
                    user=user,
                    bundle_id=matched_audience,
                    provider=SocialIdentity.Provider.APPLE,
                    provider_uid=subject,
                )
                created_user = True
            except IntegrityError:
                identity = LoginService._load_apple_identity_for_update(
                    bundle_id=matched_audience,
                    subject=subject,
                    request_id=request_id,
                )
                if not identity:
                    raise APIError("apple_identity_bind_failed", code=50032, status_code=500)
                user = identity.user
                created_user = False
            flow_logger.info(
                "Apple 渠道用户首次注册成功",
                extra={
                    "action": "user.register",
                    "request_id": request_id,
                    "channel": "apple",
                    "user_id": user.id,
                    "bundle_id": matched_audience,
                },
            )

        LoginAudit.objects.create(
            user=user,
            provider=LoginAudit.LoginProvider.APPLE,
            outcome=LoginAudit.LoginOutcome.SUCCESS,
            ip_address=ip_address or "",
            user_agent=user_agent or "",
            bundle_id=matched_audience,
            device_id=device_id or "",
            raw_claims={
                "sub": subject,
                "aud": payload.get("aud"),
                "email": email_from_token,
                "email_verified": payload.get("email_verified"),
                "apple_user_identifier": user_identifier or "",
            },
            request_id=request_id or "",
        )

        result = LoginService._issue_tokens(user)
        result["email"] = user.email or chosen_email
        result["display_name"] = (user.first_name or chosen_name).strip() or "Apple User"
        result["is_new_user"] = created_user
        flow_logger.info(
            "Apple 登录鉴权成功并签发令牌",
            extra={
                "action": "auth.apple.authenticate",
                "outcome": "success",
                "request_id": request_id,
                "user_id": user.id,
                "is_new_user": created_user,
                "bundle_id": matched_audience,
            },
        )
        return result

    @staticmethod
    def _issue_tokens(user) -> dict[str, Any]:
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token
        expires_in = int(access["exp"] - time.time())
        return {
            "user_id": user.id,
            "access_token": str(access),
            "refresh_token": str(refresh),
            "expires_in": expires_in,
            "token_type": "Bearer",
        }
