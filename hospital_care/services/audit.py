from __future__ import annotations

from typing import Any

from backoffice.audit import write_audit_log


ALLOWED_AUDIT_KEYS = {
    "hospital_id",
    "department_id",
    "doctor_id",
    "agent_id",
    "thread_id",
    "message_id",
    "staff_id",
    "user_id",
    "member_id",
    "knowledge_base_id",
    "version",
    "status",
    "publication_status",
    "service_status",
    "attention_level",
    "doctor_attention_level",
    "reason",
    "end_reason",
    "role",
    "code",
    "name",
    "service_mode",
    "employee_no",
    "license_status",
    "profile_status",
    "review_action",
    "command_key",
    "binding_id",
    "profile_id",
    "embedding_binding_id",
    "vector_status",
    "document_id",
    "document_count",
    "chunk_count",
    "indexed_revision",
}


class _SafeAuditRequest:
    def __init__(self, request, payload: dict[str, Any] | None):
        self.user = getattr(request, "user", None)
        self.method = getattr(request, "method", "")
        self.path = getattr(request, "path", "")
        self.request_id = getattr(request, "request_id", "")
        self.META = getattr(request, "META", {})
        self.data = payload or {}


def sanitize_hospital_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if key in ALLOWED_AUDIT_KEYS}


def write_hospital_audit_log(
    request,
    *,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    status_code: int = 200,
    extra: dict[str, Any] | None = None,
):
    raw = {}
    if isinstance(getattr(request, "data", None), dict):
        raw.update(sanitize_hospital_payload(request.data))
    if extra:
        raw.update(sanitize_hospital_payload(extra))
    write_audit_log(
        _SafeAuditRequest(request, raw),
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id or ""),
        status_code=status_code,
        response_payload={"ok": True, "resource_id": str(resource_id or "")},
    )
