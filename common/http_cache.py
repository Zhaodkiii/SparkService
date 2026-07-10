import hashlib
import json


def normalize_etag(value: str | None) -> str:
    if not value:
        return ""
    result = value.strip()
    if result.startswith("W/"):
        result = result[2:]
    return result.strip('"')


def etag_matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    if if_none_match.strip() == "*":
        return True
    current = normalize_etag(etag)
    return any(normalize_etag(item) == current for item in if_none_match.split(","))


def build_etag(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return f"\"{digest}\""
