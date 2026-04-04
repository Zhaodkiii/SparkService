import logging

logger = logging.getLogger(__name__)


class EmailProvider:
    """
    Email sending abstraction.

    For local/dev we keep it as a stub to avoid external side effects.
    """

    @staticmethod
    def send_otp(*, email: str, code: str, request_id: str, provider_uid: str = ""):
        logger.info("send_email_otp email=%s provider_uid=%s request_id=%s code=%s", email, provider_uid, request_id, code)

