from __future__ import annotations

import logging
from typing import Any

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.auth.tokens import SparkRefreshToken
from accounts.models import AccountDeviceSession, TrustedDevice
from common.exceptions import APIError

flow_logger = logging.getLogger("accounts.flow")


class DeviceSessionService:
    DEVICE_SESSION_REVOKED = "device_session_revoked"
    DEVICE_SESSION_REPLACED = "device_session_replaced"
    DEVICE_SESSION_NOT_FOUND = "device_session_not_found"
    DEVICE_MISMATCH = "device_mismatch"

    @staticmethod
    def _claims_from_validated_token(validated_token: Any) -> dict:
        """SimpleJWT 传入的是 Token 对象，需读取 `.payload`；不能对 Token 直接 `dict()`。"""
        if isinstance(validated_token, dict):
            return validated_token
        payload = getattr(validated_token, "payload", None)
        if payload is not None:
            return dict(payload)
        return dict(validated_token)

    @staticmethod
    def claims_require_device_session(claims: dict) -> bool:
        """仅带 device_session_id 的移动端 token 需要做单设备会话校验；后台 Admin JWT 等跳过。"""
        session_id = claims.get("device_session_id")
        return session_id is not None and str(session_id).strip() != ""

    @staticmethod
    def _raise_api(msg: str, *, code: int = 40104) -> None:
        raise APIError(msg, code=code, status_code=401)

    @staticmethod
    def _get_or_create_trusted_device(*, user, bundle_id: str, device_id: str) -> TrustedDevice:
        bundle_id = (bundle_id or "").strip()
        device_id = (device_id or "").strip()
        if not bundle_id or not device_id:
            raise APIError("bundle_id and device_id are required for login", code=40024, status_code=400)

        from accounts.services.device_service import DeviceService

        return DeviceService.ensure_user_device_profile_from_anonymous(
            user=user,
            bundle_id=bundle_id,
            device_id=device_id,
        )

    @staticmethod
    def _blacklist_refresh_jti(jti: str) -> None:
        jti = (jti or "").strip()
        if not jti:
            return
        try:
            outstanding_token = apps.get_model("token_blacklist", "OutstandingToken")
            blacklisted_token = apps.get_model("token_blacklist", "BlacklistedToken")
        except LookupError:
            return
        token = outstanding_token.objects.filter(jti=jti).first()
        if token:
            blacklisted_token.objects.get_or_create(token=token)

    @staticmethod
    def _revoke_same_installation_other_users(
        *,
        bundle_id: str,
        device_id: str,
        except_user,
        request_id: str = "",
    ) -> None:
        """同一安装实例切换到新用户：撤销其他用户设备行与同安装 ACTIVE 会话（ACCOUNTS-000003）。"""
        bundle_id = (bundle_id or "").strip()
        device_id = (device_id or "").strip()
        if not bundle_id or not device_id:
            return

        TrustedDevice.objects.filter(
            bundle_id=bundle_id,
            device_id=device_id,
            user__isnull=False,
        ).exclude(user=except_user).update(is_revoked=True)

        other_sessions = list(
            AccountDeviceSession.objects.select_for_update()
            .filter(
                bundle_id=bundle_id,
                device_id=device_id,
                status=AccountDeviceSession.Status.ACTIVE,
            )
            .exclude(user=except_user)
            .select_related("trusted_device")
        )
        for old in other_sessions:
            old.status = AccountDeviceSession.Status.REVOKED
            old.revoked_reason = "replaced_by_other_user_on_install"
            old.save(update_fields=["status", "revoked_reason", "updated_at"])
            DeviceSessionService._blacklist_refresh_jti(old.refresh_jti)
            flow_logger.info(
                "device.session.revoked_on_install_user_switch",
                extra={
                    "action": "device.session.activate",
                    "request_id": request_id,
                    "user_id": old.user_id,
                    "session_id": old.id,
                    "except_user_id": except_user.id,
                },
            )

    @staticmethod
    def _resolve_logout_session(*, user, claims: dict | None = None) -> AccountDeviceSession | None:
        """优先按 token claims 的 device_session_id 定位；否则回退用户 ACTIVE 会话。"""
        if claims and DeviceSessionService.claims_require_device_session(claims):
            try:
                return DeviceSessionService._load_session_from_claims(user=user, claims=claims)
            except APIError:
                return None
        return DeviceSessionService.get_active_session(user=user)

    @staticmethod
    @transaction.atomic
    def logout_current_session(*, user, request_id: str = "", claims: dict | None = None) -> None:
        """主动退出：标记当前会话与 trusted_device 为失效（ACCOUNTS-000003）。"""
        session = DeviceSessionService._resolve_logout_session(user=user, claims=claims)
        if session is None:
            return

        session = (
            AccountDeviceSession.objects.select_for_update()
            .filter(id=session.id)
            .select_related("trusted_device")
            .first()
        )
        if session is None:
            return

        session.status = AccountDeviceSession.Status.LOGGED_OUT
        session.revoked_reason = "user_logout"
        session.save(update_fields=["status", "revoked_reason", "updated_at"])
        DeviceSessionService._blacklist_refresh_jti(session.refresh_jti)

        trusted_device = session.trusted_device
        if trusted_device is not None:
            trusted_device.is_revoked = True
            trusted_device.save(update_fields=["is_revoked", "last_seen"])

        flow_logger.info(
            "device.session.logged_out",
            extra={
                "action": "device.session.logout",
                "request_id": request_id,
                "user_id": user.id,
                "session_id": session.id,
            },
        )

    @staticmethod
    @transaction.atomic
    def activate_session_on_login(*, user, bundle_id: str, device_id: str, request_id: str = "") -> AccountDeviceSession:
        bundle_id = (bundle_id or "").strip()
        device_id = (device_id or "").strip()
        DeviceSessionService._revoke_same_installation_other_users(
            bundle_id=bundle_id,
            device_id=device_id,
            except_user=user,
            request_id=request_id,
        )

        trusted_device = DeviceSessionService._get_or_create_trusted_device(
            user=user,
            bundle_id=bundle_id,
            device_id=device_id,
        )
        trusted_device.is_revoked = False
        trusted_device.save(update_fields=["is_revoked", "last_seen"])

        active_sessions = list(
            AccountDeviceSession.objects.select_for_update()
            .filter(user=user, status=AccountDeviceSession.Status.ACTIVE)
            .select_related("trusted_device")
        )

        for old in active_sessions:
            if old.trusted_device_id == trusted_device.id:
                continue
            old.status = AccountDeviceSession.Status.REVOKED
            old.revoked_reason = "replaced_by_new_device"
            old.save(update_fields=["status", "revoked_reason", "updated_at"])
            DeviceSessionService._blacklist_refresh_jti(old.refresh_jti)
            if old.trusted_device_id:
                TrustedDevice.objects.filter(pk=old.trusted_device_id).update(is_revoked=True)
            flow_logger.info(
                "device.session.revoked_on_login",
                extra={
                    "action": "device.session.activate",
                    "request_id": request_id,
                    "user_id": user.id,
                    "old_session_id": old.id,
                    "old_device_id": old.device_id,
                },
            )

        existing = next((s for s in active_sessions if s.trusted_device_id == trusted_device.id), None)
        if existing:
            existing.bundle_id = (bundle_id or "").strip()
            existing.device_id = (device_id or "").strip()
            existing.session_version += 1
            existing.revoked_reason = ""
            existing.replaced_by = None
            existing.save(
                update_fields=[
                    "bundle_id",
                    "device_id",
                    "session_version",
                    "revoked_reason",
                    "replaced_by",
                    "updated_at",
                ]
            )
            return existing

        session = AccountDeviceSession.objects.create(
            user=user,
            trusted_device=trusted_device,
            bundle_id=(bundle_id or "").strip(),
            device_id=(device_id or "").strip(),
            session_version=1,
            status=AccountDeviceSession.Status.ACTIVE,
        )
        flow_logger.info(
            "device.session.activated",
            extra={
                "action": "device.session.activate",
                "request_id": request_id,
                "user_id": user.id,
                "session_id": session.id,
                "device_id": session.device_id,
            },
        )
        return session

    @staticmethod
    def issue_tokens_for_session(
        *,
        user,
        session: AccountDeviceSession,
        bundle_id: str,
        device_id: str,
    ) -> dict[str, Any]:
        import time

        refresh = SparkRefreshToken.for_device_session(
            user=user,
            session=session,
            bundle_id=bundle_id,
            device_id=device_id,
        )
        access = refresh.access_token
        session.refresh_jti = str(refresh.get("jti", "") or "")
        session.last_refreshed_at = timezone.now()
        session.save(update_fields=["refresh_jti", "last_refreshed_at", "updated_at"])

        expires_in = int(access["exp"] - time.time())
        return {
            "user_id": user.id,
            "access_token": str(access),
            "refresh_token": str(refresh),
            "expires_in": expires_in,
            "token_type": "Bearer",
        }

    @staticmethod
    def activate_and_issue_tokens(*, user, bundle_id: str, device_id: str, request_id: str = "") -> dict[str, Any]:
        session = DeviceSessionService.activate_session_on_login(
            user=user,
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
        )
        return DeviceSessionService.issue_tokens_for_session(
            user=user,
            session=session,
            bundle_id=bundle_id,
            device_id=device_id,
        )

    @staticmethod
    def get_active_session(*, user) -> AccountDeviceSession | None:
        return (
            AccountDeviceSession.objects.filter(user=user, status=AccountDeviceSession.Status.ACTIVE)
            .select_related("trusted_device")
            .first()
        )

    @staticmethod
    def _load_session_from_claims(*, user, claims: dict) -> AccountDeviceSession:
        session_id = claims.get("device_session_id")
        if not session_id:
            raise APIError(
                DeviceSessionService.DEVICE_SESSION_NOT_FOUND,
                code=40106,
                status_code=401,
            )
        try:
            session = AccountDeviceSession.objects.select_related("trusted_device").get(id=int(session_id), user=user)
        except (AccountDeviceSession.DoesNotExist, TypeError, ValueError):
            raise APIError(
                DeviceSessionService.DEVICE_SESSION_NOT_FOUND,
                code=40106,
                status_code=401,
            ) from None
        return session

    @staticmethod
    def _validate_session_state(*, session: AccountDeviceSession, user) -> None:
        if session.status == AccountDeviceSession.Status.REVOKED:
            reason = (session.revoked_reason or "").strip()
            if reason == "replaced_by_new_device":
                DeviceSessionService._raise_api(DeviceSessionService.DEVICE_SESSION_REPLACED, code=40105)
            DeviceSessionService._raise_api(DeviceSessionService.DEVICE_SESSION_REVOKED, code=40104)

        if session.status != AccountDeviceSession.Status.ACTIVE:
            DeviceSessionService._raise_api(DeviceSessionService.DEVICE_SESSION_REVOKED, code=40104)

        active = DeviceSessionService.get_active_session(user=user)
        if active is None:
            DeviceSessionService._raise_api(DeviceSessionService.DEVICE_SESSION_NOT_FOUND, code=40106)
        if active.id != session.id:
            DeviceSessionService._raise_api(DeviceSessionService.DEVICE_SESSION_REPLACED, code=40105)

    @staticmethod
    def _validate_device_match(*, claims: dict, bundle_id: str, device_id: str) -> None:
        token_bundle = (claims.get("bundle_id") or "").strip()
        token_device = (claims.get("device_id") or "").strip()
        req_bundle = (bundle_id or "").strip()
        req_device = (device_id or "").strip()

        if req_device and token_device and req_device != token_device:
            DeviceSessionService._raise_api(DeviceSessionService.DEVICE_MISMATCH, code=40107)
        if req_bundle and token_bundle and req_bundle != token_bundle:
            DeviceSessionService._raise_api(DeviceSessionService.DEVICE_MISMATCH, code=40107)

    @staticmethod
    def validate_refresh_request(
        *,
        refresh_token_str: str,
        bundle_id: str = "",
        device_id: str = "",
    ) -> tuple[Any, AccountDeviceSession, dict]:
        try:
            refresh = RefreshToken(refresh_token_str)
        except TokenError as exc:
            raise APIError("token_not_valid", code=40102, status_code=401) from exc

        user_id = refresh.get("user_id")
        User = get_user_model()
        user = User.objects.filter(id=user_id).first()
        if not user or not user.is_active:
            raise APIError("user_inactive", code=40103, status_code=401)

        claims = dict(refresh.payload)
        session = DeviceSessionService._load_session_from_claims(user=user, claims=claims)
        DeviceSessionService._validate_session_state(session=session, user=user)
        DeviceSessionService._validate_device_match(claims=claims, bundle_id=bundle_id, device_id=device_id)

        token_version = int(claims.get("session_version") or 0)
        if token_version and token_version != session.session_version:
            DeviceSessionService._raise_api(DeviceSessionService.DEVICE_SESSION_REVOKED, code=40104)

        return user, session, claims

    @staticmethod
    def rotate_tokens_after_refresh(
        *,
        user,
        session: AccountDeviceSession,
        old_refresh_str: str,
        bundle_id: str,
        device_id: str,
    ) -> dict[str, Any]:
        DeviceSessionService._blacklist_refresh_jti(session.refresh_jti)
        return DeviceSessionService.issue_tokens_for_session(
            user=user,
            session=session,
            bundle_id=bundle_id or session.bundle_id,
            device_id=device_id or session.device_id,
        )

    @staticmethod
    def validate_access_claims(*, user, validated_token: Any) -> None:
        claims = DeviceSessionService._claims_from_validated_token(validated_token)
        if not DeviceSessionService.claims_require_device_session(claims):
            return
        try:
            session = DeviceSessionService._load_session_from_claims(user=user, claims=claims)
            DeviceSessionService._validate_session_state(session=session, user=user)
            token_version = int(claims.get("session_version") or 0)
            if token_version and token_version != session.session_version:
                raise AuthenticationFailed(DeviceSessionService.DEVICE_SESSION_REVOKED)
        except APIError as exc:
            raise AuthenticationFailed(exc.msg) from exc

    @staticmethod
    def validate_authenticated_device_register(*, user, bundle_id: str, device_id: str) -> None:
        active = DeviceSessionService.get_active_session(user=user)
        if active is None:
            DeviceSessionService._raise_api(DeviceSessionService.DEVICE_SESSION_NOT_FOUND, code=40106)

        trusted_device = active.trusted_device
        if trusted_device is None or trusted_device.is_revoked:
            DeviceSessionService._raise_api(DeviceSessionService.DEVICE_SESSION_REVOKED, code=40104)

        req_bundle = (bundle_id or "").strip()
        req_device = (device_id or "").strip()
        if req_device and active.device_id != req_device:
            DeviceSessionService._raise_api(DeviceSessionService.DEVICE_SESSION_REPLACED, code=40105)
        if req_bundle and active.bundle_id != req_bundle:
            DeviceSessionService._raise_api(DeviceSessionService.DEVICE_SESSION_REPLACED, code=40105)

    @staticmethod
    def apns_trusted_device_for_user(*, user) -> TrustedDevice | None:
        session = DeviceSessionService.get_active_session(user=user)
        if not session:
            return None
        dev = session.trusted_device
        if not dev or dev.is_revoked:
            return None
        if not dev.notifications_enabled:
            return None
        if not (dev.push_token or "").strip():
            return None
        return dev
