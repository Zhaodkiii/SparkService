"""Construct public OSS URLs for ManagedFile records (same rules as download view)."""

from urllib.parse import quote

from django.conf import settings


def managed_file_download_url(file_record) -> str:
    """
    Return a direct OSS URL when ``object_key`` is set; otherwise return ``file_path`` if it looks like HTTP(S).
    """
    fp = (getattr(file_record, "file_path", None) or "").strip()
    if fp.startswith("http://") or fp.startswith("https://"):
        return fp

    object_key = (getattr(file_record, "object_key", None) or "").strip()
    if not object_key:
        return ""

    endpoint = (getattr(settings, "ALIYUN_OSS_ENDPOINT", None) or "").strip()
    bucket = (getattr(settings, "ALIYUN_OSS_BUCKET", None) or "").strip()
    if not endpoint or not bucket:
        return ""

    normalized = endpoint if endpoint.startswith("http") else f"https://{endpoint}"
    if normalized.endswith("/"):
        normalized = normalized[:-1]
    if bucket not in normalized:
        normalized = normalized.replace("://", f"://{bucket}.", 1)
    key = quote(object_key.lstrip("/"), safe="/")
    return f"{normalized}/{key}"
