"""Shared account display masking."""

def mask_email(email: str, *, reveal: bool) -> str:
    text = (email or "").strip()
    if not text:
        return ""
    if reveal or is_anonymized_user_type(text):
        return text
    if "@" not in text:
        return text[:1] + "***"
    local, domain = text.split("@", 1)
    masked_local = (local[:1] + "***") if local else "***"
    return f"{masked_local}@{domain}"

def mask_phone(phone: str, *, reveal: bool) -> str:
    text = (phone or "").strip()
    if not text:
        return ""
    if reveal:
        return text
    if len(text) <= 4:
        return "***"
    return text[:3] + "****" + text[-2:]


def is_anonymized_user_type(text: str) -> bool:
    return text.endswith("@anonymized.local") or text.startswith("deleted_user_")
