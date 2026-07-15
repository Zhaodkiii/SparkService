"""Resolve client bundle_id into the shared account identity scope."""

from django.conf import settings


class IdentityScopeService:
    """
    Map a real client bundle_id to the SocialIdentity storage scope.

    SocialIdentity.bundle_id stores identity_scope (may be shared across Apps),
    while OTP / LoginAudit / TrustedDevice / AccountDeviceSession keep the real
    client bundle_id.
    """

    @staticmethod
    def resolve(bundle_id: str) -> str:
        normalized = (bundle_id or "").strip()
        if not normalized:
            return ""
        aliases = getattr(settings, "ACCOUNT_IDENTITY_SCOPE_ALIASES", None) or {}
        return aliases.get(normalized, normalized)
