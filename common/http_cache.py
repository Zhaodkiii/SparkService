import hashlib
import json


def normalize_etag(value: str | None) -> str:
    if not value:
        return ""
    result = value.strip()
    if result.startswith("W/"):
        result = result[2:]
    return result.strip('"')


def build_etag(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return f"\"{digest}\""
