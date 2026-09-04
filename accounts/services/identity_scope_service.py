"""Resolve client bundle_id into the shared account identity scope."""

from django.conf import settings

from common.exceptions import APIError


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

    @staticmethod
    def get_admin_scope_options() -> list[dict]:
        aliases = getattr(settings, "ACCOUNT_IDENTITY_SCOPE_ALIASES", None) or {}
        scopes = sorted({str(scope).strip() for scope in aliases.values() if str(scope).strip()})
        return [{"value": scope, "label": scope} for scope in scopes]

    @staticmethod
    def resolve_admin_scope(value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise APIError("identity_scope_required", code=41303, status_code=400)
        valid = {opt["value"] for opt in IdentityScopeService.get_admin_scope_options()}
        if normalized not in valid:
            raise APIError("identity_scope_invalid", code=41304, status_code=400)
        return IdentityScopeService.resolve(normalized)
