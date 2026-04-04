from typing import Any

from backoffice.models import AdminAuditLog


SENSITIVE_KEYS = {"password", "refresh", "access", "token", "key", "api_key"}


def _sanitize(data: Any):
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
