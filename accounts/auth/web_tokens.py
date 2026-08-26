from __future__ import annotations

from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import AccountWebSession


class SparkWebRefreshToken(RefreshToken):
    """Refresh/access token pair scoped to an AccountWebSession (CHAT-WEB-019).

    Claims carry `web_session_id` / `web_session_version` / `session_class=web`
    and never device claims (`device_session_id`, `device_id`, `bundle_id`).
    """

    SESSION_CLASS_WEB = "web"

    @classmethod
    def for_web_session(cls, *, user, session: AccountWebSession) -> "SparkWebRefreshToken":
        token = cls.for_user(user)
        claims = {
            "web_session_id": str(session.id),
            "web_session_version": session.session_version,
            "session_class": SparkWebRefreshToken.SESSION_CLASS_WEB,
        }
        for key, value in claims.items():
            token[key] = value
            token.access_token[key] = value
        return token
