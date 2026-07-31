import logging
from typing import Any

from accounts.models import LoginAudit
from common.exceptions import APIError

logger = logging.getLogger("accounts.flow")


class LoginAuditService:
    @staticmethod
    def write_success(
        *,
        user,
        provider: str,
        bundle_id: str,
        device_id: str = "",
        request_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
        raw_claims: dict[str, Any] | None = None,
    ) -> None:
        LoginAuditService._create(
            user=user,
            provider=provider,
            outcome=LoginAudit.LoginOutcome.SUCCESS,
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            raw_claims=raw_claims,
        )

    @staticmethod
    def write_failure(
        *,
        provider: str,
        bundle_id: str = "",
        device_id: str = "",
        request_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
        status_code: int | None = None,
        error_code: int | None = None,
        error_message: str = "",
        raw_claims: dict[str, Any] | None = None,
        user=None,
    ) -> None:
        claims = dict(raw_claims or {})
        if status_code is not None:
            claims["status_code"] = status_code
        if error_code is not None:
            claims["error_code"] = error_code
        if error_message:
            claims["error_message"] = (error_message or "")[:255]

        LoginAuditService._create(
            user=user,
            provider=provider,
            outcome=LoginAudit.LoginOutcome.FAILED,
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            raw_claims=claims or None,
        )

    @staticmethod
    def write_failure_from_api_error(
        *,
        exc: APIError,
        provider: str,
        bundle_id: str = "",
        device_id: str = "",
        request_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
        raw_claims: dict[str, Any] | None = None,
        user=None,
    ) -> None:
        LoginAuditService.write_failure(
            provider=provider,
            bundle_id=bundle_id,
            device_id=device_id,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            status_code=getattr(exc, "status_code", 400),
            error_code=getattr(exc, "code", None),
            error_message=str(getattr(exc, "msg", exc)),
            raw_claims=raw_claims,
            user=user,
        )

    @staticmethod
    def _create(**kwargs) -> None:
        try:
            LoginAudit.objects.create(**kwargs)
        except Exception as exc:
            logger.warning(
                "login.audit.write_failed request_id=%s provider=%s outcome=%s reason=%s",
                kwargs.get("request_id", ""),
                kwargs.get("provider", ""),
                kwargs.get("outcome", ""),
                str(exc),
            )
