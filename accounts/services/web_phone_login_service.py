"""Web 手机验证码登录编排（CHAT-WEB-020C）。

与移动端 /otp/phone/* 完全隔离的会话签发路径：
- 复用 OTPService 的 OTP 校验与账号解析，但签发 AccountWebSession-backed token。
- 不创建/更新/撤销 TrustedDevice、AccountDeviceSession。
- 不 import / 调用 DeviceSessionService。
- IdentityScopeService 复用同一 SocialIdentity 作用域，保证命中同一 User。
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

from accounts.services.identity_scope_service import IdentityScopeService
from accounts.services.otp_service import OTPService
from accounts.services.web_session_service import WebSessionService
from common.exceptions import APIError

flow_logger = logging.getLogger("accounts.flow")


class WebPhoneLoginService:
    WEB_PHONE_LOGIN_DISABLED = "web_phone_login_disabled"
    WEB_PHONE_LOGIN_MISCONFIGURED = "web_phone_login_misconfigured"

    @staticmethod
    def _web_service_id() -> str:
        return (getattr(settings, "WEB_AUTH_SERVICE_ID", "") or "").strip()

    @staticmethod
    def _require_enabled() -> str:
        if not getattr(settings, "WEB_PHONE_OTP_LOGIN_ENABLED", False):
            raise APIError(WebPhoneLoginService.WEB_PHONE_LOGIN_DISABLED, code=50375, status_code=503)
        service_id = WebPhoneLoginService._web_service_id()
        if not service_id:
            raise APIError(WebPhoneLoginService.WEB_PHONE_LOGIN_MISCONFIGURED, code=50376, status_code=503)
        # Web Service ID 必须映射到移动主身份作用域，否则会形成账号身份孤岛。
        if IdentityScopeService.resolve(service_id) == service_id:
            raise APIError(WebPhoneLoginService.WEB_PHONE_LOGIN_MISCONFIGURED, code=50376, status_code=503)
        return service_id

    @staticmethod
    def request_otp(*, phone_number: str, scene: str, ip_address: str, request_id: str) -> dict[str, Any]:
        service_id = WebPhoneLoginService._require_enabled()
        flow_logger.info(
            "auth.phone_otp.web.request.begin",
            extra={"action": "auth.phone_otp.web.request", "request_id": request_id, "channel": "web", "service_id": service_id},
        )
        return OTPService.request_phone_otp(
            phone_number=phone_number,
            provider_uid="",
            bundle_id=service_id,
            device_id="",
            ip_address=ip_address,
            request_id=request_id,
            scene=(scene or "").strip() or "login",
        )

    @staticmethod
    def verify_and_issue_tokens(*, otp_id: str, phone_number: str, code: str, ip_address: str, user_agent: str, request_id: str) -> dict[str, Any]:
        service_id = WebPhoneLoginService._require_enabled()
        flow_logger.info(
            "auth.phone_otp.web.verify.begin",
            extra={"action": "auth.phone_otp.web.verify", "request_id": request_id, "channel": "web", "service_id": service_id},
        )

        def issue_web_tokens(user) -> dict[str, Any]:
            # Web 会话域：独立生命周期，绝不进入设备会话域。
            session = WebSessionService.create_session(
                user=user,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )
            return {
                **WebSessionService.issue_tokens_for_session(user=user, session=session),
                "session_class": "web",
            }

        return OTPService.verify_phone_otp_and_resolve_account(
            otp_id=otp_id,
            phone_number=phone_number,
            code=code,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            bundle_id=service_id,
            device_id="",
            device_secret="",
            token_issuer=issue_web_tokens,
            audit_claims={"channel": "web", "session_class": "web"},
        )