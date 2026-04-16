import json
from typing import Optional

from django.conf import settings

try:
    from alibabacloud_dysmsapi20170525.client import Client as DysmsapiClient  # type: ignore
    from alibabacloud_tea_openapi import models as open_api_models  # type: ignore
    from alibabacloud_dysmsapi20170525 import models as dysms_models  # type: ignore
    from alibabacloud_tea_util import models as util_models  # type: ignore
except Exception:  # pragma: no cover
    DysmsapiClient = None
    open_api_models = None
    dysms_models = None
    util_models = None


class AliyunSMSProvider:
    """Aliyun SMS provider for generic notification messages."""

    @staticmethod
    def _build_client() -> Optional["DysmsapiClient"]:
        if DysmsapiClient is None or open_api_models is None:
            return None

        access_key_id = (getattr(settings, "ALIYUN_SMS_ACCESS_KEY_ID", "") or "").strip()
        access_key_secret = (getattr(settings, "ALIYUN_SMS_ACCESS_KEY_SECRET", "") or "").strip()
        endpoint = (getattr(settings, "ALIYUN_SMS_ENDPOINT", "") or "dysmsapi.aliyuncs.com").strip()
        if not access_key_id or not access_key_secret:
            return None

        cfg = open_api_models.Config(access_key_id=access_key_id, access_key_secret=access_key_secret)
        cfg.endpoint = endpoint
        return DysmsapiClient(cfg)

    @staticmethod
    def send(*, phone_number: str, title: str, body: str) -> tuple[bool, str, str]:
        """
        Returns:
            (ok, reason, provider_message_id)
        """
        if dysms_models is None or util_models is None:
            return False, "aliyun_sms_sdk_missing", ""

        sign_name = (getattr(settings, "ALIYUN_SMS_SIGN_NAME", "") or "").strip()
        template_code = (getattr(settings, "ALIYUN_SMS_NOTIFICATION_TEMPLATE_CODE", "") or "").strip()
        if not sign_name or not template_code:
            return False, "aliyun_sms_template_not_configured", ""

        client = AliyunSMSProvider._build_client()
        if client is None:
            return False, "aliyun_sms_client_unavailable", ""

        to = (phone_number or "").strip()
        if not to:
            return False, "phone_number_missing", ""

        content = (body or "").strip()
        if title:
            content = f"{title} {content}".strip()

        request = dysms_models.SendSmsRequest(
            sign_name=sign_name,
            template_code=template_code,
            phone_numbers=to,
            template_param=json.dumps({"title": title or "", "body": body or "", "content": content}),
        )
        runtime = util_models.RuntimeOptions()

        try:
            response = client.send_sms_with_options(request, runtime)
        except Exception as exc:  # noqa: BLE001
            return False, f"sms_exception:{exc}", ""

        resp_body = getattr(response, "body", None)
        req_id = (getattr(resp_body, "request_id", "") or "").strip()
        code = (getattr(resp_body, "code", "") or "").strip()
        message = (getattr(resp_body, "message", "") or "").strip()

        if getattr(response, "status_code", 0) == 200 and code == "OK":
            return True, "", req_id
        return False, f"{code or 'SMS_ERROR'}:{message or 'unknown'}", req_id

    @staticmethod
    def send_login_code(*, phone_number: str, code: str) -> tuple[bool, str, str]:
        if dysms_models is None or util_models is None:
            return False, "aliyun_sms_sdk_missing", ""

        sign_name = (getattr(settings, "ALIYUN_SMS_SIGN_NAME", "") or "").strip()
        template_code = (getattr(settings, "ALIYUN_SMS_OTP_TEMPLATE_CODE", "") or "").strip()
        if not sign_name or not template_code:
            return False, "aliyun_sms_template_not_configured", ""

        client = AliyunSMSProvider._build_client()
        if client is None:
            return False, "aliyun_sms_client_unavailable", ""

        to = (phone_number or "").strip()
        otp_code = (code or "").strip()
        if not to:
            return False, "phone_number_missing", ""
        if not otp_code:
            return False, "otp_code_missing", ""

        request = dysms_models.SendSmsRequest(
            sign_name=sign_name,
            template_code=template_code,
            phone_numbers=to,
            template_param=json.dumps({"code": otp_code}),
        )
        runtime = util_models.RuntimeOptions()

        try:
            response = client.send_sms_with_options(request, runtime)
        except Exception as exc:  # noqa: BLE001
            return False, f"sms_exception:{exc}", ""

        resp_body = getattr(response, "body", None)
        req_id = (getattr(resp_body, "request_id", "") or "").strip()
        code_value = (getattr(resp_body, "code", "") or "").strip()
        message = (getattr(resp_body, "message", "") or "").strip()

        if getattr(response, "status_code", 0) == 200 and code_value == "OK":
            return True, "", req_id
        return False, f"{code_value or 'SMS_ERROR'}:{message or 'unknown'}", req_id
