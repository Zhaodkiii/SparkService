from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

try:
    from alibabacloud_dysmsapi20170525 import models as dysms_models  # type: ignore
    from alibabacloud_dysmsapi20170525.client import Client as DysmsapiClient  # type: ignore
    from alibabacloud_tea_openapi import models as open_api_models  # type: ignore
    from alibabacloud_tea_util import models as util_models  # type: ignore
except Exception:  # pragma: no cover
    DysmsapiClient = None
    open_api_models = None
    dysms_models = None
    util_models = None


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SMSProviderResult:
    accepted: bool
    unknown: bool
    reason: str
    biz_id: str = ""
    request_id: str = ""
    code: str = ""
    status: str = ""
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class SMSDeliveryQueryResult:
    normalized_status: str
    reason: str = ""
    biz_id: str = ""
    request_id: str = ""
    code: str = ""
    provider_status: str = ""
    delivered_at: datetime | None = None
    payload: dict[str, Any] | None = None


class AliyunSMSProvider:
    """Aliyun SMS provider for generic notification messages."""

    @staticmethod
    def _mask_phone_number(phone_number: str) -> str:
        text = (phone_number or "").strip()
        digits = "".join(ch for ch in text if ch.isdigit())
        if len(digits) >= 8:
            return f"{digits[:3]}****{digits[-4:]}"
        if len(digits) >= 4:
            return f"****{digits[-4:]}"
        return "***" if text else ""

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
    def otp_readiness_error() -> str:
        if dysms_models is None or util_models is None:
            return "aliyun_sms_sdk_missing"
        sign_name = (getattr(settings, "ALIYUN_SMS_SIGN_NAME", "") or "").strip()
        template_code = (getattr(settings, "ALIYUN_SMS_OTP_TEMPLATE_CODE", "") or "").strip()
        if not sign_name or not template_code:
            return "aliyun_sms_template_not_configured"
        if AliyunSMSProvider._build_client() is None:
            return "aliyun_sms_client_unavailable"
        return ""

    @staticmethod
    def _normalize_exception(exc: Exception) -> tuple[bool, str]:
        text = (str(exc) or "").strip()
        lowered = text.lower()
        if any(part in lowered for part in ("timeout", "timed out", "connection reset", "temporarily unavailable", "readtimeoutexception")):
            return True, text or "provider_timeout"
        return False, text or type(exc).__name__

    @staticmethod
    def _normalize_query_phone_number(phone_number: str) -> str:
        raw = (phone_number or "").strip()
        if not raw:
            return ""
        digits = "".join(ch for ch in raw if ch.isdigit())
        if raw.startswith("+86") and len(digits) == 13 and digits.startswith("86"):
            return digits[2:]
        if len(digits) == 11 and digits.startswith("1"):
            return digits
        return raw.lstrip("+")

    @staticmethod
    def _extract_send_details(resp_body: Any) -> list[Any]:
        container = getattr(resp_body, "sms_send_detail_d_t_os", None) or getattr(resp_body, "sms_send_detail_dtos", None)
        if container is None:
            return []
        details = (
            getattr(container, "sms_send_detail_d_t_o", None)
            or getattr(container, "sms_send_detail_dto", None)
            or getattr(container, "SmsSendDetailDTO", None)
            or []
        )
        if isinstance(details, list):
            return details
        if isinstance(details, tuple):
            return list(details)
        return [details] if details else []

    @staticmethod
    def _normalize_query_send_date(send_date: datetime | None) -> datetime:
        dt = send_date or timezone.now()
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone=timezone.get_current_timezone())
        return timezone.localtime(dt, timezone=ZoneInfo("Asia/Shanghai"))

    @staticmethod
    def _send_request(*, phone_number: str, template_code: str, template_param: dict[str, Any]) -> SMSProviderResult:
        if dysms_models is None or util_models is None:
            return SMSProviderResult(False, False, "aliyun_sms_sdk_missing")

        sign_name = (getattr(settings, "ALIYUN_SMS_SIGN_NAME", "") or "").strip()
        if not sign_name or not template_code:
            return SMSProviderResult(False, False, "aliyun_sms_template_not_configured")

        client = AliyunSMSProvider._build_client()
        if client is None:
            return SMSProviderResult(False, False, "aliyun_sms_client_unavailable")

        to = (phone_number or "").strip()
        if not to:
            return SMSProviderResult(False, False, "phone_number_missing")

        request = dysms_models.SendSmsRequest(
            sign_name=sign_name,
            template_code=template_code,
            phone_numbers=to,
            template_param=json.dumps(template_param),
        )
        runtime = util_models.RuntimeOptions()

        try:
            response = client.send_sms_with_options(request, runtime)
        except Exception as exc:  # noqa: BLE001
            unknown, reason = AliyunSMSProvider._normalize_exception(exc)
            return SMSProviderResult(False, unknown, f"sms_exception:{reason}", payload={"exception": reason})

        resp_body = getattr(response, "body", None)
        request_id = (getattr(resp_body, "request_id", "") or "").strip()
        biz_id = (getattr(resp_body, "biz_id", "") or "").strip()
        code = (getattr(resp_body, "code", "") or "").strip()
        message = (getattr(resp_body, "message", "") or "").strip()
        payload = {
            "status_code": getattr(response, "status_code", 0),
            "request_id": request_id,
            "biz_id": biz_id,
            "code": code,
            "message": message,
            "sign_name": sign_name,
            "phone_number_masked": AliyunSMSProvider._mask_phone_number(to),
            "template_code": template_code,
            "template_param_keys": sorted(str(key) for key in template_param.keys()),
            "template_param": template_param,
        }

        if getattr(response, "status_code", 0) == 200 and code == "OK":
            return SMSProviderResult(True, False, "", biz_id=biz_id, request_id=request_id, code=code, status="accepted", payload=payload)
        return SMSProviderResult(False, False, f"{code or 'SMS_ERROR'}:{message or 'unknown'}", biz_id=biz_id, request_id=request_id, code=code or "SMS_ERROR", status="failed", payload=payload)

    @staticmethod
    def send(*, phone_number: str, title: str, body: str) -> SMSProviderResult:
        content = (body or "").strip()
        if title:
            content = f"{title} {content}".strip()
        template_code = (getattr(settings, "ALIYUN_SMS_NOTIFICATION_TEMPLATE_CODE", "") or "").strip()
        return AliyunSMSProvider._send_request(
            phone_number=phone_number,
            template_code=template_code,
            template_param={"title": title or "", "body": body or "", "content": content},
        )

    @staticmethod
    def send_login_code(*, phone_number: str, code: str) -> SMSProviderResult:
        otp_code = (code or "").strip()
        if not otp_code:
            return SMSProviderResult(False, False, "otp_code_missing")
        template_code = (getattr(settings, "ALIYUN_SMS_OTP_TEMPLATE_CODE", "") or "").strip()
        return AliyunSMSProvider._send_request(
            phone_number=phone_number,
            template_code=template_code,
            template_param={"code": otp_code},
        )

    @staticmethod
    def query_send_details(
        *,
        phone_number: str,
        biz_id: str,
        send_date: datetime | None = None,
        current_page: int = 1,
        page_size: int = 10,
        request_id: str = "",
    ) -> SMSDeliveryQueryResult:
        if dysms_models is None or util_models is None:
            logger.warning(
                "aliyun.sms.query_send_details.failed",
                extra={"action": "aliyun.sms.query_send_details", "request_id": request_id or "", "biz_id": (biz_id or "").strip(), "reason": "aliyun_sms_sdk_missing"},
            )
            return SMSDeliveryQueryResult("unknown", reason="aliyun_sms_sdk_missing")

        client = AliyunSMSProvider._build_client()
        if client is None:
            logger.warning(
                "aliyun.sms.query_send_details.failed",
                extra={"action": "aliyun.sms.query_send_details", "request_id": request_id or "", "biz_id": (biz_id or "").strip(), "reason": "aliyun_sms_client_unavailable"},
            )
            return SMSDeliveryQueryResult("unknown", reason="aliyun_sms_client_unavailable")

        to = AliyunSMSProvider._normalize_query_phone_number(phone_number)
        biz = (biz_id or "").strip()
        if not to or not biz:
            logger.warning(
                "aliyun.sms.query_send_details.failed",
                extra={"action": "aliyun.sms.query_send_details", "request_id": request_id or "", "biz_id": biz, "phone_number": to or "", "reason": "phone_or_biz_id_missing"},
            )
            return SMSDeliveryQueryResult("unknown", reason="phone_or_biz_id_missing")

        dt = AliyunSMSProvider._normalize_query_send_date(send_date)
        logger.info(
            "aliyun.sms.query_send_details.begin biz_id=%s phone_number=%s send_date=%s current_page=%s page_size=%s",
            biz,
            to,
            dt.strftime("%Y%m%d"),
            current_page,
            page_size,
            extra={
                "action": "aliyun.sms.query_send_details",
                "request_id": request_id or "",
                "biz_id": biz,
                "phone_number": to,
                "send_date": dt.strftime("%Y%m%d"),
                "current_page": current_page,
                "page_size": page_size,
            },
        )
        request = dysms_models.QuerySendDetailsRequest(
            phone_number=to,
            biz_id=biz,
            send_date=dt.strftime("%Y%m%d"),
            current_page=current_page,
            page_size=page_size,
        )
        runtime = util_models.RuntimeOptions()
        started_at = time.monotonic()
        try:
            response = client.query_send_details_with_options(request, runtime)
        except Exception as exc:  # noqa: BLE001
            unknown, reason = AliyunSMSProvider._normalize_exception(exc)
            logger.warning(
                "aliyun.sms.query_send_details.failed",
                extra={
                    "action": "aliyun.sms.query_send_details",
                    "request_id": request_id or "",
                    "biz_id": biz,
                    "phone_number": to,
                    "send_date": dt.strftime("%Y%m%d"),
                    "duration_ms": int((time.monotonic() - started_at) * 1000),
                    "reason": f"query_exception:{reason}",
                    "unknown": unknown,
                },
            )
            return SMSDeliveryQueryResult("unknown" if unknown else "delivery_failed", reason=f"query_exception:{reason}", biz_id=biz, payload={"exception": reason})

        resp_body = getattr(response, "body", None)
        code = (getattr(resp_body, "code", "") or "").strip()
        message = (getattr(resp_body, "message", "") or "").strip()
        provider_request_id = (getattr(resp_body, "request_id", "") or "").strip()
        total_count = int(getattr(resp_body, "total_count", 0) or 0)
        details = AliyunSMSProvider._extract_send_details(resp_body)
        payload = {
            "status_code": getattr(response, "status_code", 0),
            "request_id": provider_request_id,
            "code": code,
            "message": message,
            "phone_number_masked": AliyunSMSProvider._mask_phone_number(to),
            "biz_id": biz,
            "total_count": total_count,
            "detail_count": len(details),
        }
        if getattr(response, "status_code", 0) != 200 or code != "OK":
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.warning(
                "aliyun.sms.query_send_details.result biz_id=%s phone_number=%s send_date=%s duration_ms=%s provider_request_id=%s provider_code=%s provider_status=failed total_count=%s normalized_status=unknown reason=%s",
                biz,
                to,
                dt.strftime("%Y%m%d"),
                duration_ms,
                provider_request_id or "-",
                code or "QUERY_ERROR",
                total_count,
                f"{code or 'QUERY_ERROR'}:{message or 'unknown'}",
                extra={
                    "action": "aliyun.sms.query_send_details",
                    "request_id": request_id or "",
                    "biz_id": biz,
                    "phone_number": to,
                    "send_date": dt.strftime("%Y%m%d"),
                    "duration_ms": duration_ms,
                    "provider_request_id": provider_request_id,
                    "provider_code": code or "QUERY_ERROR",
                    "provider_status": "failed",
                    "total_count": total_count,
                    "normalized_status": "unknown",
                    "reason": f"{code or 'QUERY_ERROR'}:{message or 'unknown'}",
                },
            )
            return SMSDeliveryQueryResult("unknown", reason=f"{code or 'QUERY_ERROR'}:{message or 'unknown'}", biz_id=biz, request_id=provider_request_id, code=code or "QUERY_ERROR", provider_status="failed", payload=payload)
        if total_count <= 0 or not details:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.info(
                "aliyun.sms.query_send_details.result biz_id=%s phone_number=%s send_date=%s duration_ms=%s provider_request_id=%s provider_code=%s provider_status=accepted total_count=%s normalized_status=accepted reason=-",
                biz,
                to,
                dt.strftime("%Y%m%d"),
                duration_ms,
                provider_request_id or "-",
                code or "-",
                total_count,
                extra={
                    "action": "aliyun.sms.query_send_details",
                    "request_id": request_id or "",
                    "biz_id": biz,
                    "phone_number": to,
                    "send_date": dt.strftime("%Y%m%d"),
                    "duration_ms": duration_ms,
                    "provider_request_id": provider_request_id,
                    "provider_code": code,
                    "provider_status": "accepted",
                    "total_count": total_count,
                    "normalized_status": "accepted",
                    "reason": "",
                },
            )
            return SMSDeliveryQueryResult("accepted", biz_id=biz, request_id=provider_request_id, code=code, provider_status="accepted", payload=payload)

        detail = details[0]
        send_status = str(getattr(detail, "send_status", "") or "").strip()
        err_code = str(getattr(detail, "err_code", "") or "").strip()
        receive_date = str(getattr(detail, "receive_date", "") or "").strip()
        delivered_at: datetime | None = None
        if receive_date:
            try:
                delivered_at = datetime.strptime(receive_date, "%Y-%m-%d %H:%M:%S")
                delivered_at = timezone.make_aware(delivered_at, timezone.get_current_timezone())
            except Exception:  # noqa: BLE001
                delivered_at = None
        detail_payload = {
            **payload,
            "send_status": send_status,
            "err_code": err_code,
            "receive_date": receive_date,
            "out_id": str(getattr(detail, "out_id", "") or "").strip(),
        }
        normalized_status = "accepted"
        result_reason = ""
        result_code = code
        if send_status == "3":
            normalized_status = "delivered"
        elif send_status == "2":
            normalized_status = "delivery_failed"
            result_reason = err_code or "carrier_delivery_failed"
            result_code = err_code or code
        duration_ms = int((time.monotonic() - started_at) * 1000)
        logger.info(
            "aliyun.sms.query_send_details.result biz_id=%s phone_number=%s send_date=%s duration_ms=%s provider_request_id=%s provider_code=%s provider_status=%s total_count=%s normalized_status=%s reason=%s",
            biz,
            to,
            dt.strftime("%Y%m%d"),
            duration_ms,
            provider_request_id or "-",
            result_code or "-",
            send_status or "accepted",
            total_count,
            normalized_status,
            result_reason or "-",
            extra={
                "action": "aliyun.sms.query_send_details",
                "request_id": request_id or "",
                "biz_id": biz,
                "phone_number": to,
                "send_date": dt.strftime("%Y%m%d"),
                "duration_ms": duration_ms,
                "provider_request_id": provider_request_id,
                "provider_code": result_code,
                "provider_status": send_status or "accepted",
                "total_count": total_count,
                "normalized_status": normalized_status,
                "reason": result_reason,
            },
        )
        if normalized_status == "delivered":
            return SMSDeliveryQueryResult("delivered", biz_id=biz, request_id=provider_request_id, code=code, provider_status=send_status, payload=detail_payload, reason="", delivered_at=delivered_at)
        if normalized_status == "delivery_failed":
            return SMSDeliveryQueryResult("delivery_failed", biz_id=biz, request_id=provider_request_id, code=result_code, provider_status=send_status, payload=detail_payload, reason=result_reason, delivered_at=delivered_at)
        return SMSDeliveryQueryResult("accepted", biz_id=biz, request_id=provider_request_id, code=code, provider_status=send_status or "accepted", payload=detail_payload)
