import logging
import uuid
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.utils import IntegrityError
from django.utils import timezone

from accounts.models import AccountDeviceSession, LoginAudit, SocialIdentity
from accounts.services.login_audit_service import LoginAuditService
from accounts.services.device_credential_service import DeviceCredentialService
from accounts.services.identity_scope_service import IdentityScopeService
from accounts.services.login_service import LoginService
from common.exceptions import APIError

flow_logger = logging.getLogger("accounts.flow")


class DeviceLoginService:
    """设备游客账户登录：创建/恢复 device SocialIdentity 并签发标准会话。"""

    @staticmethod
    def is_enabled(*, bundle_id: str) -> bool:
        if not getattr(settings, "DEVICE_ACCOUNT_LOGIN_ENABLED", True):
            return False
        allowed = getattr(settings, "DEVICE_ACCOUNT_LOGIN_ALLOWED_BUNDLES", None)
        if not allowed:
            return True
        return (bundle_id or "").strip() in allowed

    @staticmethod
    def is_device_account(*, user) -> bool:
        providers = set(
            SocialIdentity.objects.filter(user=user).values_list("provider", flat=True)
        )
        formal = {
            SocialIdentity.Provider.APPLE,
            SocialIdentity.Provider.GOOGLE,
            SocialIdentity.Provider.PHONE,
            SocialIdentity.Provider.EMAIL,
        }
        return bool(providers) and providers.isdisjoint(formal) and (
            SocialIdentity.Provider.DEVICE in providers
        )

    @staticmethod
    def _create_device_user(*, device_id: str):
        User = get_user_model()
        digest = DeviceCredentialService.device_id_audit_tail(device_id) or "unknown"
        display_name_base = f"device_{digest}"
        display_name = display_name_base
        display_suffix = 1
        while User.objects.filter(first_name=display_name).exists():
            display_suffix += 1
            display_name = f"{display_name_base}_{display_suffix}"

        # 设备身份的唯一性由 SocialIdentity 约束负责；用户名使用随机后缀，避免
        # 并发首次登录在 exists()+create() 之间发生竞态。
        username = f"{display_name_base}_{uuid.uuid4().hex[:16]}"
        user = User.objects.create(
            username=username,
            first_name=display_name,
            email="",
            is_active=True,
        )
        user.set_unusable_password()
        user.save(update_fields=["password", "is_active"])
        return user

    @staticmethod
    def _load_device_identity(*, identity_scope: str, device_id: str):
        return (
            SocialIdentity.objects.select_for_update()
            .select_related("user")
            .filter(
                bundle_id=identity_scope,
                provider=SocialIdentity.Provider.DEVICE,
                provider_uid=device_id,
            )
            .first()
        )

    @staticmethod
    def authenticate_and_issue_tokens(
        *,
        bundle_id: str,
        device_id: str,
        device_secret: str,
        ip_address: str = "",
        user_agent: str = "",
        request_id: str = "",
        attestation: str = "",
    ) -> dict[str, Any]:
        del attestation  # 预留 App Attest / DeviceCheck
        real_bundle_id = (bundle_id or "").strip()
        normalized_device_id = (device_id or "").strip()
        if not real_bundle_id or not normalized_device_id:
            raise APIError("bundle_id_or_device_id_required", code=40061, status_code=400)
        if not DeviceLoginService.is_enabled(bundle_id=real_bundle_id):
            raise APIError("device_account_login_disabled", code=40361, status_code=403)

        identity_scope = IdentityScopeService.resolve(real_bundle_id)
        # 凭证校验在登录事务外完成，保证失败计数不被回滚。
        DeviceCredentialService.verify_or_register(
            identity_scope=identity_scope,
            device_id=normalized_device_id,
            device_secret=device_secret,
            ip_address=ip_address,
            request_id=request_id,
        )

        with transaction.atomic():
            return DeviceLoginService._authenticate_after_credential(
                real_bundle_id=real_bundle_id,
                identity_scope=identity_scope,
                normalized_device_id=normalized_device_id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )

    @staticmethod
    def _authenticate_after_credential(
        *,
        real_bundle_id: str,
        identity_scope: str,
        normalized_device_id: str,
        ip_address: str,
        user_agent: str,
        request_id: str,
    ) -> dict[str, Any]:
        from accounts.services.access_control_service import AccessControlService

        identity = DeviceLoginService._load_device_identity(
            identity_scope=identity_scope,
            device_id=normalized_device_id,
        )
        created_user = False
        account_resolution = "device_account_login"
        User = get_user_model()

        def _create_device_user_guarded(*, old_user_id: int | None = None):
            if old_user_id is not None:
                AccessControlService.check(
                    user_id=old_user_id,
                    provider=LoginAudit.LoginProvider.DEVICE,
                    bundle_id=real_bundle_id,
                    device_id=normalized_device_id,
                    request_id=request_id or "",
                    ip_address=ip_address or "",
                    user_agent=user_agent or "",
                )
            AccessControlService.check_device_registration(
                device_id=normalized_device_id,
                provider=LoginAudit.LoginProvider.DEVICE,
                bundle_id=real_bundle_id,
                request_id=request_id or "",
                ip_address=ip_address or "",
                user_agent=user_agent or "",
            )
            return DeviceLoginService._create_device_user(device_id=normalized_device_id)

        if identity is not None:
            user = identity.user
            if not user.is_active:
                flow_logger.info(
                    "device.login.inactive_user_recreate",
                    extra={
                        "action": "auth.device.login",
                        "request_id": request_id,
                        "old_user_id": user.id,
                        "device_id_hash": DeviceCredentialService.device_id_audit_tail(normalized_device_id),
                    },
                )
                user = _create_device_user_guarded(old_user_id=user.id)
                identity.user = user
                identity.save(update_fields=["user", "updated_at"])
                created_user = True
                account_resolution = "device_account_recreated"
        else:
            user = _create_device_user_guarded()
            try:
                SocialIdentity.objects.create(
                    user=user,
                    bundle_id=identity_scope,
                    provider=SocialIdentity.Provider.DEVICE,
                    provider_uid=normalized_device_id,
                )
                created_user = True
                account_resolution = "device_account_created"
            except IntegrityError:
                orphan_id = user.id
                identity = DeviceLoginService._load_device_identity(
                    identity_scope=identity_scope,
                    device_id=normalized_device_id,
                )
                if identity is None:
                    raise APIError("device_identity_conflict", code=40961, status_code=409)
                User.objects.filter(id=orphan_id).delete()
                user = identity.user
                created_user = False
                account_resolution = "device_account_login"
                if not user.is_active:
                    user = _create_device_user_guarded(old_user_id=user.id)
                    identity.user = user
                    identity.save(update_fields=["user", "updated_at"])
                    created_user = True
                    account_resolution = "device_account_recreated"

        identities = AccessControlService._collect_user_identities(user=user)
        AccessControlService.check(
            user_id=user.id,
            email=(user.email or ""),
            phone=AccessControlService._phone_for_user(user),
            provider=LoginAudit.LoginProvider.DEVICE,
            bundle_id=real_bundle_id,
            device_id=normalized_device_id,
            request_id=request_id or "",
            ip_address=ip_address or "",
            user_agent=user_agent or "",
        )
        for email in identities["emails"]:
            AccessControlService.check(
                email=email,
                provider=LoginAudit.LoginProvider.DEVICE,
                bundle_id=real_bundle_id,
                device_id=normalized_device_id,
                request_id=request_id or "",
                ip_address=ip_address or "",
                user_agent=user_agent or "",
            )
        for phone in identities["phones"]:
            AccessControlService.check(
                phone=phone,
                provider=LoginAudit.LoginProvider.DEVICE,
                bundle_id=real_bundle_id,
                device_id=normalized_device_id,
                request_id=request_id or "",
                ip_address=ip_address or "",
                user_agent=user_agent or "",
            )

        LoginAuditService.write_success(
            user=user,
            provider=LoginAudit.LoginProvider.DEVICE,
            bundle_id=real_bundle_id,
            device_id=normalized_device_id,
            request_id=request_id or "",
            ip_address=ip_address or "",
            user_agent=user_agent or "",
            raw_claims={
                "identity_scope": identity_scope,
                "account_resolution": account_resolution,
                "device_id_hash": DeviceCredentialService.device_id_audit_tail(normalized_device_id),
            },
        )

        LoginService._prepare_login_entitlements(
            user=user,
            bundle_id=real_bundle_id,
            device_id=normalized_device_id,
            request_id=request_id,
        )
        result = LoginService._apply_is_pro(
            user=user,
            payload=LoginService._issue_tokens(
                user,
                bundle_id=real_bundle_id,
                device_id=normalized_device_id,
                request_id=request_id,
            ),
        )
        result.update(
            {
                "email": user.email or "",
                "display_name": user.first_name or user.username,
                "is_new_user": created_user,
                "sign_in_method": SocialIdentity.Provider.DEVICE,
                "is_device_account": True,
                "account_resolution": account_resolution,
                "identity_scope": identity_scope,
            }
        )
        flow_logger.info(
            "device.login.success",
            extra={
                "action": "auth.device.login",
                "request_id": request_id,
                "user_id": user.id,
                "account_resolution": account_resolution,
                "is_new_user": created_user,
                "device_id_hash": DeviceCredentialService.device_id_audit_tail(normalized_device_id),
            },
        )
        return result

    @staticmethod
    def revoke_active_sessions_for_user(*, user, reason: str = "device_account_upgraded") -> None:
        now = timezone.now()
        AccountDeviceSession.objects.filter(
            user=user,
            status=AccountDeviceSession.Status.ACTIVE,
        ).update(
            status=AccountDeviceSession.Status.REVOKED,
            revoked_reason=reason,
            updated_at=now,
        )
