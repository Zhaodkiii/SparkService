from typing import Any
from datetime import date, datetime
import hashlib

from backoffice.models import AdminAuditLog


SENSITIVE_KEYS = {
    "password",
    "refresh",
    "access",
    "token",
    "key",
    "api_key",
    "text",
    "content",
    "message",
    "introduction",
    "attention_note",
    "id_card",
    "phone",
    "mobile",
    "secret",
    "provider_uid",
    "provider_uid_plain",
}


def _sanitize(data: Any):
    # Ensure JSONField-safe primitives: datetime/date -> isoformat string.
    if isinstance(data, (datetime, date)):
        return data.isoformat()
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if str(key).lower() in SENSITIVE_KEYS:
                result[key] = "***"
            else:
                result[key] = _sanitize(value)
        return result
    if isinstance(data, list):
        return [_sanitize(item) for item in data]
    return data


def write_audit_log(request, *, action: str, resource_type: str = "", resource_id: str = "", status_code: int = 200, response_payload=None):
    user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
    payload = None
    if isinstance(getattr(request, "data", None), dict):
        payload = _sanitize(dict(request.data))

    try:
        AdminAuditLog.objects.create(
            user=user,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            method=request.method,
            path=request.path,
            status_code=status_code,
            request_id=getattr(request, "request_id", "") or "",
            ip_address=request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")) or "",
            user_agent=request.META.get("HTTP_USER_AGENT", "") or "",
            request_payload=payload,
            response_payload=_sanitize(response_payload),
        )
    except Exception:
        # Audit log should never break business endpoints.
        return


def _sha256_digest(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def write_admin_identity_audit(
    request,
    *,
    action: str,
    target_user_id: int,
    provider: str,
    identity_scope: str,
    old_uid: str = "",
    new_uid: str = "",
    result: str,
    error_code=None,
    remaining_count=None,
    status_code: int = 200,
):
    from backoffice.serializers import mask_provider_uid

    payload = {
        "operator_user_id": getattr(getattr(request, "user", None), "id", None),
        "target_user_id": target_user_id,
        "provider": provider,
        "identity_scope": identity_scope,
        "old_uid_masked": mask_provider_uid(provider=provider, provider_uid=old_uid) if old_uid else "",
        "new_uid_masked": mask_provider_uid(provider=provider, provider_uid=new_uid) if new_uid else "",
        "old_uid_sha256": _sha256_digest(old_uid),
        "new_uid_sha256": _sha256_digest(new_uid),
        "remaining_count": remaining_count,
        "result": result,
        "error_code": error_code,
        "request_id": getattr(request, "request_id", "") or "",
    }
    write_audit_log(
        request,
        action=action,
        resource_type="auth_identity",
        resource_id=str(target_user_id),
        status_code=status_code,
        response_payload=payload,
    )
