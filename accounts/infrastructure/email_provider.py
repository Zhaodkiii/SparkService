import logging
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


class EmailProvider:
    """
    Email sending abstraction.

    For local/dev we keep it as a stub to avoid external side effects.
    """

    @staticmethod
    def send_otp(*, email: str, code: str, request_id: str, provider_uid: str = ""):
        logger.info("send_email_otp email=%s provider_uid=%s request_id=%s code=%s", email, provider_uid, request_id, code)

    @staticmethod
    def send_notification(*, email: str, title: str, body: str, request_id: str = "") -> tuple[bool, str, str]:
        """
        Returns:
            (ok, reason, provider_message_id)
        """
        to = (email or "").strip()
        if not to:
            return False, "email_missing", ""

        subject = (title or "通知").strip() or "通知"
        content = (body or "").strip()
        provider_message_id = f"email-{request_id or 'manual'}"
        from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip() or None
        try:
            send_mail(
                subject=subject,
                message=content,
                from_email=from_email,
                recipient_list=[to],
                fail_silently=False,
            )
            logger.info("send_email_notification email=%s request_id=%s subject=%s", to, request_id, subject)
            return True, "", provider_message_id
        except Exception as exc:  # noqa: BLE001
            logger.exception("send_email_notification_failed email=%s request_id=%s", to, request_id)
            return False, str(exc), ""
