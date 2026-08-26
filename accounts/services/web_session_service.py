"""AccountWebSession lifecycle management (CHAT-WEB-019B).

Isolation contract with DeviceSessionService:
- This service never reads or writes AccountDeviceSession / TrustedDevice.
- DeviceSessionService never reads or writes AccountWebSession.
- Cross-domain revocation (account ban / deactivate / logout-all) must call
  both services explicitly.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.auth.web_tokens import SparkWebRefreshToken
from accounts.models import AccountWebSession
from common.exceptions import APIError

flow_logger = logging.getLogger("accounts.flow")


class WebSessionService:
    WEB_SESSION_REVOKED = "web_session_revoked"
    WEB_SESSION_EXPIRED = "web_session_expired"
    WEB_SESSION_NOT_FOUND = "web_session_not_found"
    WEB_SESSION_REFRESH_REPLAYED = "web_session_refresh_replayed"
    WEB_SESSION_CLASS_CONFLICT = "token_session_class_conflict"
    WEB_SESSION_STORE_UNAVAILABLE = "web_session_store_unavailable"

    @staticmethod
    def _notify_session_invalidated_on_commit(session_id, reason: str) -> None:
        from chat_sync.events import ChatSyncNotifier

        def notify() -> None:
            try:
                ChatSyncNotifier.notify_web_session_invalidated(str(session_id), reason=reason)
            except Exception:  # pragma: no cover - channel infrastructure failure
                flow_logger.exception("web.session.invalidation_notify_failed session_id=%s", session_id)

        transaction.on_commit(
            notify
        )

    @staticmethod
    def _hash_value(value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            return ""
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _refresh_lifetime_seconds() -> int:
        lifetime = getattr(settings, "SIMPLE_JWT", {}).get(
            "REFRESH_TOKEN_LIFETIME", timezone.timedelta(days=30)
        )
        return int(lifetime.total_seconds())

    @staticmethod
    def claims_require_web_session(claims: dict) -> bool:
        """Web token: carries web_session_id and session_class=web."""
        session_id = claims.get("web_session_id")
        session_class = (claims.get("session_class") or "").strip()
        return session_id is not None and str(session_id).strip() != "" and session_class == "web"

    @staticmethod
    def claims_conflict_session_classes(claims: dict) -> bool:
        """A token must not carry both device and web session claims."""
        device_id_claim = claims.get("device_session_id")
        web_id_claim = claims.get("web_session_id")
        return (
            device_id_claim is not None
            and str(device_id_claim).strip() != ""
            and web_id_claim is not None
            and str(web_id_claim).strip() != ""
        )

    @staticmethod
    def _raise_api(msg: str, *, code: int) -> None:
        raise APIError(msg, code=code, status_code=401)

    @staticmethod
    def _log_session_event(event: str, *, session: AccountWebSession, request_id: str = "", **extra) -> None:
        flow_logger.info(
            event,
            extra={
                "action": "web.session",
                "request_id": request_id,
                "user_id": session.user_id,
                "web_session_id_tail": str(session.id)[-8:],
                "session_status": session.status,
                **extra,
            },
        )

    @staticmethod
    def create_session(
        *,
        user,
        ip_address: str = "",
        user_agent: str = "",
        request_id: str = "",
    ) -> AccountWebSession:
        """Create a new independent Web session. Never touches device sessions."""
        try:
            session = AccountWebSession.objects.create(
                user=user,
                status=AccountWebSession.Status.ACTIVE,
                session_version=1,
                user_agent_hash=WebSessionService._hash_value(user_agent),
                ip_prefix_hash=WebSessionService._hash_value((ip_address or "").split(",")[0].strip()),
                expires_at=timezone.now() + timezone.timedelta(seconds=WebSessionService._refresh_lifetime_seconds()),
                request_id=request_id,
            )
        except (OperationalError, ProgrammingError) as exc:
            flow_logger.error(
                "web.session.store_unavailable",
                extra={"action": "web.session.create", "request_id": request_id, "reason": str(exc)},
            )
            raise APIError(WebSessionService.WEB_SESSION_STORE_UNAVAILABLE, code=50373, status_code=503) from exc
        WebSessionService._log_session_event("web.session.created", session=session, request_id=request_id)
        return session

    @staticmethod
    def _load_session_from_claims(*, user, claims: dict) -> AccountWebSession:
        session_id = claims.get("web_session_id")
        if not session_id:
            WebSessionService._raise_api(WebSessionService.WEB_SESSION_NOT_FOUND, code=40183)
        try:
            parsed_id = UUID(str(session_id))
        except (ValueError, AttributeError, TypeError):
            WebSessionService._raise_api(WebSessionService.WEB_SESSION_NOT_FOUND, code=40183)
        try:
            return AccountWebSession.objects.get(id=parsed_id, user=user)
        except AccountWebSession.DoesNotExist:
            WebSessionService._raise_api(WebSessionService.WEB_SESSION_NOT_FOUND, code=40183)

    @staticmethod
    def _validate_session_state(*, session: AccountWebSession, user) -> None:
        now = timezone.now()
        if session.status == AccountWebSession.Status.ACTIVE and session.expires_at and session.expires_at <= now:
            # Lazy expiry: mark once, then report as expired.
            AccountWebSession.objects.filter(pk=session.pk, status=AccountWebSession.Status.ACTIVE).update(
                status=AccountWebSession.Status.EXPIRED,
                revoked_at=now,
                revoked_reason="expired",
            )
            session.status = AccountWebSession.Status.EXPIRED
            session.revoked_reason = "expired"
            WebSessionService._raise_api(WebSessionService.WEB_SESSION_EXPIRED, code=40182)

        if session.status == AccountWebSession.Status.EXPIRED:
            WebSessionService._raise_api(WebSessionService.WEB_SESSION_EXPIRED, code=40182)
        if session.status == AccountWebSession.Status.LOGGED_OUT:
            WebSessionService._raise_api(WebSessionService.WEB_SESSION_REVOKED, code=40181)
        if session.status != AccountWebSession.Status.ACTIVE:
            WebSessionService._raise_api(WebSessionService.WEB_SESSION_REVOKED, code=40181)
        if not getattr(user, "is_active", False):
            WebSessionService._raise_api(WebSessionService.WEB_SESSION_REVOKED, code=40181)

    @staticmethod
    def _validate_version_and_jti(*, session: AccountWebSession, claims: dict) -> None:
        token_version = int(claims.get("web_session_version") or 0)
        if token_version and token_version != session.session_version:
            WebSessionService._raise_api(WebSessionService.WEB_SESSION_REVOKED, code=40181)
        presented_jti = (claims.get("jti") or "").strip()
        if session.refresh_jti_hash and presented_jti:
            if WebSessionService._hash_value(presented_jti) != session.refresh_jti_hash:
                WebSessionService._raise_api(WebSessionService.WEB_SESSION_REFRESH_REPLAYED, code=40184)

    @staticmethod
    def validate_refresh_request(*, refresh_token_str: str) -> tuple[Any, AccountWebSession, dict]:
        """Validate a Web refresh token. Never queries AccountDeviceSession."""
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
        if WebSessionService.claims_conflict_session_classes(claims):
            WebSessionService._raise_api(WebSessionService.WEB_SESSION_CLASS_CONFLICT, code=40186)
        if not WebSessionService.claims_require_web_session(claims):
            WebSessionService._raise_api(WebSessionService.WEB_SESSION_NOT_FOUND, code=40183)

        session = WebSessionService._load_session_from_claims(user=user, claims=claims)
        WebSessionService._validate_session_state(session=session, user=user)
        WebSessionService._validate_version_and_jti(session=session, claims=claims)
        return user, session, claims

    @staticmethod
    def issue_tokens_for_session(*, user, session: AccountWebSession) -> dict[str, Any]:
        refresh = SparkWebRefreshToken.for_web_session(user=user, session=session)
        access = refresh.access_token
        session.refresh_jti_hash = WebSessionService._hash_value(str(refresh.get("jti", "") or ""))
        session.last_refreshed_at = timezone.now()
        session.save(update_fields=["refresh_jti_hash", "last_refreshed_at", "updated_at"])
        expires_in = int(access["exp"] - time.time())
        return {
            "user_id": user.id,
            "access_token": str(access),
            "refresh_token": str(refresh),
            "expires_in": expires_in,
            "token_type": "Bearer",
        }

    @staticmethod
    @transaction.atomic
    def rotate_tokens_after_refresh(*, user, session: AccountWebSession) -> dict[str, Any]:
        """Rotation: bump version and replace JTI hash; old token replay is rejected later."""
        locked = (
            AccountWebSession.objects.select_for_update()
            .filter(pk=session.pk, status=AccountWebSession.Status.ACTIVE)
            .first()
        )
        if locked is None:
            WebSessionService._raise_api(WebSessionService.WEB_SESSION_REVOKED, code=40181)
        locked.session_version += 1
        locked.save(update_fields=["session_version", "updated_at"])
        session.session_version = locked.session_version
        tokens = WebSessionService.issue_tokens_for_session(user=user, session=locked)
        WebSessionService._log_session_event("web.session.refreshed", session=locked)
        return tokens

    @staticmethod
    @transaction.atomic
    def logout_current_session(*, user, request_id: str = "", claims: dict | None = None) -> None:
        """Web logout: revoke only the current Web session; mobile sessions untouched."""
        if not claims or not WebSessionService.claims_require_web_session(claims):
            return
        session = WebSessionService._load_session_from_claims(user=user, claims=claims)
        updated = AccountWebSession.objects.filter(
            pk=session.pk, status=AccountWebSession.Status.ACTIVE
        ).update(
            status=AccountWebSession.Status.LOGGED_OUT,
            revoked_at=timezone.now(),
            revoked_reason="user_logout",
            request_id=request_id,
        )
        if updated:
            WebSessionService._notify_session_invalidated_on_commit(session.pk, "user_logout")
            WebSessionService._log_session_event(
                "web.session.logged_out", session=session, request_id=request_id
            )

    @staticmethod
    def validate_access_claims(*, user, validated_token: Any) -> None:
        """Access-token validation for authenticated requests. Device tokens skip."""
        claims = validated_token if isinstance(validated_token, dict) else dict(getattr(validated_token, "payload", {}))
        if WebSessionService.claims_conflict_session_classes(claims):
            raise AuthenticationFailed(WebSessionService.WEB_SESSION_CLASS_CONFLICT)
        if not WebSessionService.claims_require_web_session(claims):
            return
        if not getattr(settings, "WEB_SESSION_DOMAIN_ENABLED", True):
            raise AuthenticationFailed(WebSessionService.WEB_SESSION_REVOKED)
        try:
            session = WebSessionService._load_session_from_claims(user=user, claims=claims)
            WebSessionService._validate_session_state(session=session, user=user)
            token_version = int(claims.get("web_session_version") or 0)
            if token_version and token_version != session.session_version:
                raise AuthenticationFailed(WebSessionService.WEB_SESSION_REVOKED)
        except APIError as exc:
            raise AuthenticationFailed(exc.msg) from exc

    @staticmethod
    @transaction.atomic
    def revoke_all_sessions_for_user(*, user, reason: str, request_id: str = "") -> int:
        """Cross-domain revocation entry (ban / deactivate / logout-all): revoke every ACTIVE web session."""
        now = timezone.now()
        session_ids = list(AccountWebSession.objects.filter(
            user=user, status=AccountWebSession.Status.ACTIVE
        ).values_list("id", flat=True))
        updated = AccountWebSession.objects.filter(
            user=user, status=AccountWebSession.Status.ACTIVE
        ).update(
            status=AccountWebSession.Status.REVOKED,
            revoked_at=now,
            revoked_reason=reason,
            request_id=request_id,
        )
        for session_id in session_ids:
            WebSessionService._notify_session_invalidated_on_commit(session_id, reason)
        if updated:
            flow_logger.info(
                "web.session.revoked_all",
                extra={
                    "action": "web.session.revoke_all",
                    "request_id": request_id,
                    "user_id": user.id,
                    "count": updated,
                    "reason": reason,
                },
            )
        return updated
