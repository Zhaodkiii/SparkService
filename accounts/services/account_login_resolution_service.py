import logging
from typing import Any, Callable

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.utils import IntegrityError

from accounts.models import LoginAudit, SocialIdentity
from accounts.services.login_audit_service import LoginAuditService
from accounts.services.device_credential_service import DeviceCredentialService
from accounts.services.device_login_service import DeviceLoginService
from accounts.services.deactivation_service import DeactivationService
from accounts.services.login_service import LoginService
from common.exceptions import APIError

flow_logger = logging.getLogger("accounts.flow")


class AccountLoginResolutionService:
    """
    正式身份统一解析器。

    只接收已验证并归一化的 provider UID；不得直接接收未验证 token / OTP。
    """

    FORMAL_PROVIDERS = {
        SocialIdentity.Provider.APPLE,
        SocialIdentity.Provider.GOOGLE,
        SocialIdentity.Provider.PHONE,
        SocialIdentity.Provider.EMAIL,
    }

    @staticmethod
    def _load_identity_for_update(*, identity_scope: str, provider: str, provider_uid: str):
        return (
            SocialIdentity.objects.select_for_update()
            .select_related("user")
            .filter(
                bundle_id=identity_scope,
                provider=provider,
                provider_uid=provider_uid,
            )
            .first()
        )

    @staticmethod
    def _load_device_identity(*, identity_scope: str, device_id: str):
        device_id = (device_id or "").strip()
        if not device_id:
            return None
        return AccountLoginResolutionService._load_identity_for_update(
            identity_scope=identity_scope,
            provider=SocialIdentity.Provider.DEVICE,
            provider_uid=device_id,
        )

    @staticmethod
    def _audit_provider(provider: str) -> str:
        if provider == SocialIdentity.Provider.APPLE:
            return LoginAudit.LoginProvider.APPLE
        if provider == SocialIdentity.Provider.GOOGLE:
            return LoginAudit.LoginProvider.GOOGLE
        if provider == SocialIdentity.Provider.PHONE:
            return LoginAudit.LoginProvider.PHONE_OTP
        if provider == SocialIdentity.Provider.EMAIL:
            return LoginAudit.LoginProvider.EMAIL_OTP
        return provider

    @staticmethod
    @transaction.atomic
    def resolve_verified_identity(
        *,
        provider: str,
        normalized_provider_uid: str,
        real_bundle_id: str,
        identity_scope: str,
        device_id: str = "",
        device_secret: str = "",
        request_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
        verified_claims: dict[str, Any] | None = None,
        create_user: Callable[[], Any],
        on_existing_user: Callable[[Any], None] | None = None,
        login_audit_provider: str | None = None,
    ) -> dict[str, Any]:
        provider = (provider or "").strip()
        provider_uid = (normalized_provider_uid or "").strip()
        scope = (identity_scope or "").strip()
        real_bundle = (real_bundle_id or "").strip()
        normalized_device_id = (device_id or "").strip()
        verified_claims = verified_claims or {}

        if provider not in AccountLoginResolutionService.FORMAL_PROVIDERS:
            raise APIError("unsupported_login_provider", code=40064, status_code=400)
        if not provider_uid or not scope or not real_bundle:
            raise APIError("bundle_id_or_provider_uid_required", code=40065, status_code=400)

        from accounts.services.access_control_service import AccessControlService

        audit_provider = login_audit_provider or AccountLoginResolutionService._audit_provider(provider)

        def _guarded_create_user(*, old_user_id: int | None = None):
            if old_user_id is not None:
                AccessControlService.check(
                    user_id=old_user_id,
                    provider=audit_provider,
                    bundle_id=real_bundle,
                    device_id=normalized_device_id,
                    request_id=request_id or "",
                    ip_address=ip_address or "",
                    user_agent=user_agent or "",
                )
            AccessControlService.check_device_registration(
                device_id=normalized_device_id,
                provider=audit_provider,
                bundle_id=real_bundle,
                request_id=request_id or "",
                ip_address=ip_address or "",
                user_agent=user_agent or "",
            )
            return create_user()

        formal = AccountLoginResolutionService._load_identity_for_update(
            identity_scope=scope,
            provider=provider,
            provider_uid=provider_uid,
        )
        device_identity = None
        # 已存在正式身份时，device_secret 只用于可选的设备账号切换上下文；
        # 正式身份本身不应因旧设备凭据异常而无法登录。首次绑定正式身份时，
        # 则必须验证已登记的设备凭据。
        if formal is None and normalized_device_id and (device_secret or "").strip():
            DeviceCredentialService.verify_or_register(
                identity_scope=scope,
                device_id=normalized_device_id,
                device_secret=device_secret,
                ip_address=ip_address,
                request_id=request_id,
                allow_register=False,
            )
            device_identity = AccountLoginResolutionService._load_device_identity(
                identity_scope=scope,
                device_id=normalized_device_id,
            )

        created_user = False
        account_resolution = "existing_identity_login"
        previous_device_account_id = None
        User = get_user_model()

        if formal is not None:
            user = formal.user
            if user.is_active:
                account_resolution = "existing_identity_login"
                if device_identity is not None and device_identity.user_id != user.id:
                    previous_device_account_id = device_identity.user_id
                    flow_logger.info(
                        "account.resolution.existing_identity_from_device",
                        extra={
                            "action": "auth.account.resolve",
                            "request_id": request_id,
                            "provider": provider,
                            "user_id": user.id,
                            "previous_device_account_id": previous_device_account_id,
                            "device_id_hash": DeviceCredentialService.device_id_audit_tail(
                                normalized_device_id
                            ),
                        },
                    )
                if on_existing_user is not None:
                    on_existing_user(user)
            else:
                # inactive：创建新用户并重绑正式身份（延续 Apple 既有策略）。
                flow_logger.info(
                    "account.resolution.formal_recreate_inactive",
                    extra={
                        "action": "auth.account.resolve",
                        "request_id": request_id,
                        "provider": provider,
                        "old_user_id": user.id,
                    },
                )
                user = _guarded_create_user(old_user_id=user.id)
                formal.user = user
                formal.save(update_fields=["user", "updated_at"])
                created_user = True
                account_resolution = "formal_account_recreated"
        else:
            # 正式身份不存在：优先升级当前有效设备账户。
            if (
                device_identity is not None
                and getattr(device_identity.user, "is_active", False)
            ):
                user = device_identity.user
                try:
                    SocialIdentity.objects.create(
                        user=user,
                        bundle_id=scope,
                        provider=provider,
                        provider_uid=provider_uid,
                    )
                except IntegrityError:
                    # 并发下正式身份可能已被创建：回读并按已有身份处理。
                    formal = AccountLoginResolutionService._load_identity_for_update(
                        identity_scope=scope,
                        provider=provider,
                        provider_uid=provider_uid,
                    )
                    if formal is None:
                        raise APIError("identity_bind_conflict", code=40962, status_code=409)
                    user = formal.user
                    if not user.is_active:
                        raise APIError("user_inactive", code=40103, status_code=401)
                    account_resolution = "existing_identity_login"
                    if on_existing_user is not None:
                        on_existing_user(user)
                else:
                    device_identity.delete()
                    DeviceLoginService.revoke_active_sessions_for_user(
                        user=user,
                        reason="device_account_upgraded",
                    )
                    account_resolution = "device_account_upgraded"
                    created_user = False
                    if on_existing_user is not None:
                        on_existing_user(user)
                    flow_logger.info(
                        "account.resolution.device_upgraded",
                        extra={
                            "action": "auth.account.resolve",
                            "request_id": request_id,
                            "provider": provider,
                            "user_id": user.id,
                            "device_id_hash": DeviceCredentialService.device_id_audit_tail(
                                normalized_device_id
                            ),
                        },
                    )
            else:
                user = _guarded_create_user()
                try:
                    SocialIdentity.objects.create(
                        user=user,
                        bundle_id=scope,
                        provider=provider,
                        provider_uid=provider_uid,
                    )
                    created_user = True
                    account_resolution = "formal_account_created"
                except IntegrityError:
                    orphan_id = user.id
                    formal = AccountLoginResolutionService._load_identity_for_update(
                        identity_scope=scope,
                        provider=provider,
                        provider_uid=provider_uid,
                    )
                    if formal is None:
                        raise APIError("identity_bind_conflict", code=40962, status_code=409)
                    User.objects.filter(id=orphan_id).delete()
                    user = formal.user
                    created_user = False
                    account_resolution = "existing_identity_login"
                    if not user.is_active:
                        raise APIError("user_inactive", code=40103, status_code=401)
                    if on_existing_user is not None:
                        on_existing_user(user)

        LoginAuditService.write_success(
            user=user,
            provider=audit_provider,
            bundle_id=real_bundle,
            device_id=normalized_device_id,
            request_id=request_id or "",
            ip_address=ip_address or "",
            user_agent=user_agent or "",
            raw_claims={
                **verified_claims,
                "identity_scope": scope,
                "account_resolution": account_resolution,
                "previous_device_account_id": previous_device_account_id,
            },
        )

        cancel_result = DeactivationService.cancel_pending_on_login(
            user=user, request_id=request_id
        )
        LoginService._prepare_login_entitlements(
            user=user,
            bundle_id=real_bundle,
            device_id=normalized_device_id,
            request_id=request_id,
        )
        result = LoginService._apply_is_pro(
            user=user,
            payload=LoginService._issue_tokens(
                user,
                bundle_id=real_bundle,
                device_id=normalized_device_id,
                request_id=request_id,
            ),
        )
        result.update(
            {
                "is_new_user": created_user,
                "sign_in_method": provider,
                "is_device_account": DeviceLoginService.is_device_account(user=user),
                "account_resolution": account_resolution,
                "identity_scope": scope,
                "deactivation_cancelled": cancel_result,
            }
        )
        return result
