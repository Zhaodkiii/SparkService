import logging
import smtplib
import ssl

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def _mask_email(email: str) -> str:
    """Redact inbox for INFO/WARNING logs (full address still used for SMTP)."""
    email = (email or "").strip()
    if not email:
        return ""
    if "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    if len(local) <= 1:
        return f"*@{domain}"
    if len(local) <= 4:
        return f"{local[0]}***@{domain}"
    return f"{local[:3]}***@{domain}"


def _smtp_recipients_refused_detail(exc: smtplib.SMTPRecipientsRefused) -> str:
    parts: list[str] = []
    for _rcp, tup in getattr(exc, "recipients", {}).items():
        if isinstance(tup, tuple) and len(tup) >= 2:
            code, reply = tup[0], tup[1]
            if isinstance(reply, bytes):
                reply = reply.decode("utf-8", "replace").strip()
            parts.append(f"{code} {reply}")
    return "; ".join(parts)[:2000]


def classify_email_send_failure(exc: Exception) -> tuple[str, str, bool]:
    """
    Classify Django send_mail / SMTP failures.

    Returns:
        error_code — stable key for APIs and DB (`error_code` column).
        error_detail — human-ish SMTP text for `error_message` / client hints.
        is_operational_noise — if True: log WARNING without traceback (normal provider rejects).
    """
    if isinstance(exc, ssl.SSLCertVerificationError):
        return (
            "ssl_cert_verify_failed",
            (str(exc) or "").strip()[:2000],
            False,
        )
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return (
            "smtp_recipient_rejected",
            _smtp_recipients_refused_detail(exc),
            True,
        )
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        text = str(exc).strip()
        return "smtp_authentication_failed", text[:2000], False
    if isinstance(exc, smtplib.SMTPSenderRefused):
        chunks: list[str] = []
        if getattr(exc, "smtp_code", None):
            chunks.append(str(exc.smtp_code))
        blob = getattr(exc, "smtp_error", b"") or b""
        if isinstance(blob, bytes):
            chunks.append(blob.decode("utf-8", "replace").strip())
        return (
            "smtp_sender_refused",
            "; ".join(x for x in chunks if x)[:2000],
            True,
        )
    if isinstance(exc, smtplib.SMTPResponseException):
        reply = getattr(exc, "smtp_error", b"") or b""
        if isinstance(reply, bytes):
            reply = reply.decode("utf-8", "replace").strip()
        code = int(getattr(exc, "smtp_code", 0) or 0)
        err_code = f"smtp_server_error_{code}" if code else "smtp_server_error"
        return err_code, reply[:2000], True
    if isinstance(exc, smtplib.SMTPException):
        return (
            f"smtp_{type(exc).__name__}",
            str(exc).strip()[:2000],
            True,
        )
    return (
        f"email_exception_{type(exc).__name__}",
        str(exc).strip()[:2000],
        False,
    )


class EmailProvider:
    """
    Email sending abstraction.

    For local/dev we keep it as a stub to avoid external side effects.
    """

    @staticmethod
    def send_otp(*, email: str, code: str, request_id: str, provider_uid: str = ""):
        logger.info(
            "send_email_otp email=%s provider_uid=%s request_id=%s",
            _mask_email(email),
            provider_uid or "-",
            request_id or "-",
        )

    @staticmethod
    def send_notification(
        *, email: str, title: str, body: str, request_id: str = "", html_body: str = ""
    ) -> tuple[bool, str, str, str]:
        """
        Returns:
            ok, error_code (empty when ok), provider_message_id, error_detail (empty when ok).
        """
        to = (email or "").strip()
        if not to:
            return False, "email_missing", "", ""

        subject = (title or "通知").strip() or "通知"
        content = (body or "").strip()
        provider_message_id = f"email-{request_id or 'manual'}"
        from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip() or None
        masked = _mask_email(to)
        try:
            message = EmailMultiAlternatives(
                subject=subject,
                body=content,
                from_email=from_email,
                to=[to],
            )
            if html_body.strip():
                message.attach_alternative(html_body, "text/html")
            message.send(fail_silently=False)
            logger.info(
                "send_email_notification email=%s request_id=%s subject=%s",
                masked,
                request_id,
                subject,
            )
            return True, "", provider_message_id, ""
        except Exception as exc:  # noqa: BLE001
            code, detail, ops_noise = classify_email_send_failure(exc)
            if ops_noise:
                logger.warning(
                    "send_email_notification_failed email=%s request_id=%s reason=%s detail=%s",
                    masked,
                    request_id or "-",
                    code,
                    (detail[:400] + "…") if len(detail) > 400 else (detail or "-"),
                )
            else:
                logger.exception(
                    "send_email_notification_failed email=%s request_id=%s reason=%s",
                    masked,
                    request_id or "-",
                    code,
                )
            return False, code, provider_message_id, detail
