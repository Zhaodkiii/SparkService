"""服务端 OSS PutObject 封装（长期 AccessKey 仅保留在服务端）。

使用已安装的 ``oss2`` SDK，并开启 ``x-oss-forbid-overwrite`` 禁止覆盖语义；
Object Key 由调用方以随机 UUID 生成，从设计上避免碰撞。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

from django.conf import settings

logger = logging.getLogger("file_manager.oss")


@dataclass(frozen=True)
class PutObjectResult:
    object_key: str
    etag: str
    request_id: str
    version_id: str
    crc64: str


@dataclass(frozen=True)
class OssObjectMeta:
    """OSS 对象元信息（不携带文件内容）。"""

    object_key: str
    content_length: int | None
    content_type: str
    etag: str


class OssUploadError(Exception):
    """OSS 上传失败；不携带密钥、文件正文等敏感信息。"""


def _bucket():
    import oss2  # 延迟导入，未安装 SDK 的环境不影响其他模块加载

    access_key_id = (getattr(settings, "ALIYUN_ACCESS_KEY_ID", "") or "").strip()
    access_key_secret = (getattr(settings, "ALIYUN_ACCESS_KEY_SECRET", "") or "").strip()
    bucket_name = (getattr(settings, "ALIYUN_OSS_BUCKET", "") or "").strip()
    endpoint = (getattr(settings, "ALIYUN_OSS_ENDPOINT", "") or "").strip()
    if not access_key_id or not access_key_secret or not bucket_name or not endpoint:
        raise OssUploadError("oss_config_missing")
    auth = oss2.Auth(access_key_id, access_key_secret)
    return oss2.Bucket(auth, endpoint, bucket_name)


def put_bytes(*, object_key: str, content: bytes, content_type: str) -> PutObjectResult:
    """上传字节内容到 OSS，禁止覆盖同名 Object。"""
    headers = {
        "Content-Type": content_type,
        "x-oss-forbid-overwrite": "true",
    }
    try:
        result = _bucket().put_object(object_key, BytesIO(content), headers=headers)
    except Exception as exc:  # oss2 异常类型多样，统一收敛
        logger.warning(
            "OSS PutObject 失败",
            extra={"object_key": object_key, "error_type": type(exc).__name__},
        )
        raise OssUploadError("oss_put_failed") from exc
    return PutObjectResult(
        object_key=object_key,
        etag=(getattr(result, "etag", "") or "").strip('"'),
        request_id=getattr(result, "request_id", "") or "",
        version_id=getattr(result, "version_id", "") or "",
        crc64=str(getattr(result, "crc64", "") or ""),
    )


def object_meta(*, object_key: str) -> OssObjectMeta:
    """读取 OSS 对象元信息；对象不存在抛 ``OssUploadError("oss_object_not_found")``。"""
    import oss2  # 延迟导入，与 _bucket 保持一致

    try:
        result = _bucket().get_object_meta(object_key)
    except oss2.exceptions.NoSuchKey as exc:
        raise OssUploadError("oss_object_not_found") from exc
    except Exception as exc:  # oss2 异常类型多样，统一收敛
        logger.warning(
            "OSS GetObjectMeta 失败",
            extra={"object_key": object_key, "error_type": type(exc).__name__},
        )
        raise OssUploadError("oss_head_failed") from exc
    headers = getattr(result, "headers", {}) or {}
    content_length: int | None = None
    raw_length = headers.get("Content-Length")
    try:
        content_length = int(raw_length) if raw_length is not None else None
    except (TypeError, ValueError):
        content_length = None
    return OssObjectMeta(
        object_key=object_key,
        content_length=content_length,
        content_type=str(headers.get("Content-Type") or ""),
        etag=str(headers.get("ETag") or "").strip('"'),
    )


def get_bytes(*, object_key: str, max_bytes: int) -> bytes:
    """下载 OSS 对象字节，超过 ``max_bytes`` 抛 ``OssUploadError("oss_object_too_large")``。

    读取流在 finally 中关闭，避免连接泄漏；不记录任何文件内容。
    """
    import oss2  # 延迟导入，与 _bucket 保持一致

    stream = None
    try:
        stream = _bucket().get_object(object_key)
        content = stream.read(max_bytes + 1)
    except oss2.exceptions.NoSuchKey as exc:
        raise OssUploadError("oss_object_not_found") from exc
    except OssUploadError:
        raise
    except Exception as exc:  # oss2 异常类型多样，统一收敛
        logger.warning(
            "OSS GetObject 失败",
            extra={"object_key": object_key, "error_type": type(exc).__name__},
        )
        raise OssUploadError("oss_get_failed") from exc
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception:  # pragma: no cover - 关闭失败不影响主流程
                pass
    if len(content) > max_bytes:
        raise OssUploadError("oss_object_too_large")
    return content
