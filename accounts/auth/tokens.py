from __future__ import annotations

from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import AccountDeviceSession


class SparkRefreshToken(RefreshToken):
    """Refresh/access token pair with device session claims for single-device login."""

    @classmethod
    def for_device_session(
        cls,
        *,
        user,
        session: AccountDeviceSession,
        bundle_id: str,
        device_id: str,
    ) -> "SparkRefreshToken":
        token = cls.for_user(user)
        claims = {
            "device_session_id": session.id,
            "session_version": session.session_version,
            "bundle_id": (bundle_id or "").strip(),
            "device_id": (device_id or "").strip(),
        }
        for key, value in claims.items():
            token[key] = value
            token.access_token[key] = value
        return token
