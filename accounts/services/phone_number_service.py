import re

from django.conf import settings

from common.exceptions import APIError


class PhoneNumberService:
    _DIAL_CODE_REGION_MAP = {
        "1": "US",
        "20": "EG",
        "27": "ZA",
        "30": "GR",
        "31": "NL",
        "32": "BE",
        "33": "FR",
        "34": "ES",
        "39": "IT",
        "44": "GB",
        "45": "DK",
        "46": "SE",
        "47": "NO",
        "49": "DE",
        "52": "MX",
        "55": "BR",
        "60": "MY",
        "61": "AU",
        "62": "ID",
        "63": "PH",
        "64": "NZ",
        "65": "SG",
        "66": "TH",
        "81": "JP",
        "82": "KR",
        "84": "VN",
        "86": "CN",
        "90": "TR",
        "91": "IN",
        "92": "PK",
        "93": "AF",
        "94": "LK",
        "95": "MM",
        "98": "IR",
        "212": "MA",
        "213": "DZ",
        "216": "TN",
        "218": "LY",
        "220": "GM",
        "221": "SN",
        "230": "MU",
        "234": "NG",
        "248": "SC",
        "251": "ET",
        "254": "KE",
        "255": "TZ",
        "256": "UG",
        "263": "ZW",
        "351": "PT",
        "352": "LU",
        "353": "IE",
        "354": "IS",
        "356": "MT",
        "357": "CY",
        "358": "FI",
        "359": "BG",
        "370": "LT",
        "371": "LV",
        "372": "EE",
        "380": "UA",
        "385": "HR",
        "386": "SI",
        "420": "CZ",
        "421": "SK",
        "852": "HK",
        "853": "MO",
        "855": "KH",
        "856": "LA",
        "886": "TW",
    }

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
    def _normalized_supported_sms_otp_regions() -> list[str]:
        configured = getattr(settings, "SMS_OTP_SUPPORTED_REGIONS", ["CN"])
        if isinstance(configured, str):
            values = [item.strip().upper() for item in configured.split(",")]
        else:
            values = [str(item).strip().upper() for item in configured]
        return [item for item in values if item]

    @staticmethod
    def _normalized_supported_sms_otp_dial_codes() -> list[str]:
        configured = getattr(settings, "SMS_OTP_SUPPORTED_DIAL_CODES", ["+86"])
        if isinstance(configured, str):
            values = [item.strip() for item in configured.split(",")]
        else:
            values = [str(item).strip() for item in configured]
        out: list[str] = []
        for value in values:
            if not value:
                continue
            digits = value.lstrip("+")
            if digits.isdigit():
                out.append(f"+{digits}")
        return out or ["+86"]

    @staticmethod
    def resolve_region(normalized_phone: str) -> tuple[str, str]:
        normalized = PhoneNumberService.normalize_e164(normalized_phone)
        digits = normalized.lstrip("+")
        for length in (3, 2, 1):
            prefix = digits[:length]
            region_code = PhoneNumberService._DIAL_CODE_REGION_MAP.get(prefix)
            if region_code:
                return region_code, f"+{prefix}"
        return "", ""

    @staticmethod
    def is_supported_sms_otp_region(normalized_phone: str) -> bool:
        region_code, dial_code = PhoneNumberService.resolve_region(normalized_phone)
        supported_regions = set(PhoneNumberService._normalized_supported_sms_otp_regions())
        supported_dial_codes = set(PhoneNumberService._normalized_supported_sms_otp_dial_codes())
        return (region_code and region_code in supported_regions) or (dial_code and dial_code in supported_dial_codes)

    @staticmethod
    def masked_display(phone_number: str) -> str:
        normalized = PhoneNumberService.normalize_e164(phone_number)
        digits = normalized.lstrip("+")
        if len(digits) <= 7:
            return normalized
        return f"+{digits[:2]}{'*' * (len(digits) - 6)}{digits[-4:]}"
