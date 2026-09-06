"""ManagedFile inline 预览：服务端从 OSS 读取并以 Content-Disposition: inline 返回。"""

from __future__ import annotations

import logging

from django.conf import settings

from file_manager.business_access import user_can_access_file, user_can_preview_file
from file_manager.models import ManagedFile
from file_manager.services.oss_object_service import OssUploadError, get_bytes

logger = logging.getLogger("file_manager.preview")

DEFAULT_MAX_BYTES = 20 * 1024 * 1024


class ManagedFilePreviewError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def preview_max_bytes() -> int:
    return int(getattr(settings, "MANAGED_FILE_PREVIEW_MAX_BYTES", DEFAULT_MAX_BYTES))


def stream_managed_file_preview(*, user, file_id) -> tuple[bytes, str, str]:
    try:
        file_id_int = int(file_id)
    except (TypeError, ValueError):
        raise ManagedFilePreviewError("file_not_found")

    file_record = (
        ManagedFile.objects.filter(id=file_id_int, is_deleted=False)
        .prefetch_related("business_relations")
        .first()
    )
    if file_record is None or not user_can_preview_file(user, file_record):
        raise ManagedFilePreviewError("file_not_found")

    object_key = (file_record.object_key or "").strip()
    if not object_key:
        raise ManagedFilePreviewError("object_key_missing")

    try:
        raw = get_bytes(object_key=object_key, max_bytes=preview_max_bytes())
    except OssUploadError as exc:
        logger.warning("ManagedFile 预览读取失败 file_id=%s: %s", file_id_int, type(exc).__name__)
        raise ManagedFilePreviewError("file_not_found") from exc

    mime = (file_record.mime_type or "application/octet-stream").strip()
    filename = file_record.original_name or "attachment"
    return raw, mime, filename
