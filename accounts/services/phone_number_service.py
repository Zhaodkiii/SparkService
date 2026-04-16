import re

from django.conf import settings

from common.exceptions import APIError


class PhoneNumberService:
    @staticmethod
    def normalize_e164(phone_number: str) -> str:
        raw = (phone_number or "").strip()
        if not raw:
            raise APIError("phone_number required", code=40031, status_code=400)

        cleaned = re.sub(r"[\s\-\(\)]", "", raw)
        if cleaned.startswith("00"):
            cleaned = f"+{cleaned[2:]}"

        if cleaned.startswith("+"):
            digits = cleaned[1:]
            if digits.isdigit() is False or not 7 <= len(digits) <= 15:
                raise APIError("invalid_phone_number", code=40032, status_code=400)
            return f"+{digits}"

        digits = re.sub(r"\D", "", cleaned)
        if not digits:
            raise APIError("invalid_phone_number", code=40032, status_code=400)

        # Mainland China mobile numbers are the primary client case.
        if len(digits) == 11 and digits.startswith("1"):
            return f"+86{digits}"

        if 11 < len(digits) <= 15:
            return f"+{digits}"

        if not 7 <= len(digits) <= 15:
            raise APIError("invalid_phone_number", code=40032, status_code=400)

        default_region = (getattr(settings, "OTP_DEFAULT_REGION_CODE", "86") or "86").strip().lstrip("+")
        if not default_region.isdigit():
            default_region = "86"
        return f"+{default_region}{digits}"

    @staticmethod
    def masked_display(phone_number: str) -> str:
        normalized = PhoneNumberService.normalize_e164(phone_number)
        digits = normalized.lstrip("+")
        if len(digits) <= 7:
            return normalized
        return f"+{digits[:2]}{'*' * (len(digits) - 6)}{digits[-4:]}"
