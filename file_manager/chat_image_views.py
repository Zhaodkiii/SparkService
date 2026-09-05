"""Web 对话图片上传会话与登记接口（CHAT-WEB-029）。

链路：客户端申请上传会话 → 使用预签名 PUT URL 直传 OSS → 调用 complete 登记。
与旧 ``/api/v1/files/register/`` 的区别：本接口用 oss2 + Pillow 校验对象真实
存在、真实大小、真实 MIME 与 MD5，客户端声明的任何字段都不被信任。

安全边界：
- 只下发预签名 URL，不返回长期 AK/SK，也不返回完整 STS 凭证；
- Object Key 使用随机 UUID，不含原始文件名与用户标识；
- 日志只记录 session_id / file_id / 错误码，不记录图片 URL 与内容。
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace

from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from PIL import Image
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from common.exceptions import APIError
from common.response import success_response
from file_manager.models import ManagedFile
from file_manager.services.oss_object_service import OssUploadError, get_bytes, object_meta
from file_manager.sts_utils import get_sts_credentials
from file_manager.url_utils import managed_file_download_url

logger = logging.getLogger("file_manager.chat_image")

# 允许的图片 MIME → Object Key 扩展名
ALLOWED_IMAGE_MIME_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
# Pillow 格式名 → MIME（与 ALLOWED_IMAGE_MIME_EXT 一一对应）
_PIL_FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}

MAX_IMAGE_FILE_SIZE = 10 * 1024 * 1024  # 单张图片最大 10 MB
SESSION_TTL_SECONDS = 30 * 60  # 上传会话 30 分钟有效
UPLOAD_URL_EXPIRES_IN = 900  # 预签名 PUT URL 15 分钟有效
OBJECT_KEY_PREFIX = "zhaodkdream/spark_service/chat/image"


class ChatImageUploadThrottle(UserRateThrottle):
    scope = "chat_image_upload"


def _session_cache_key(session_id: str) -> str:
    return f"chat_image_upload:session:{session_id}"


def _intent_cache_key(user_id: int, client_upload_id: str) -> str:
    return f"chat_image_upload:intent:{user_id}:{client_upload_id}"


def _display_url_for_key(object_key: str) -> str:
    """复用 managed_file_download_url 的拼接规则（登记前尚无 ManagedFile 行）。"""
    return managed_file_download_url(SimpleNamespace(file_path="", object_key=object_key))


def _sts_bucket():
    """用 STS 临时凭证构造 Bucket；无 STS 配置时回退静态凭证（仅开发环境）。"""
    import oss2  # 延迟导入，未安装 SDK 的环境不影响其他模块加载

    creds = get_sts_credentials()
    token = (creds.get("security_token") or "").strip()
    if token:
        auth = oss2.StsAuth(creds["access_key_id"], creds["access_key_secret"], token)
    else:
        auth = oss2.Auth(creds["access_key_id"], creds["access_key_secret"])
    return oss2.Bucket(auth, creds["endpoint"], creds["bucket_name"])


def _sign_upload_url(*, object_key: str, mime_type: str) -> str:
    """生成限定 Object Key 与 Content-Type 的预签名 PUT URL。"""
    try:
        bucket = _sts_bucket()
        return bucket.sign_url("PUT", object_key, UPLOAD_URL_EXPIRES_IN, headers={"Content-Type": mime_type})
    except Exception as exc:
        # 配置缺失（ValueError）或 STS 签发失败（RuntimeError）统一收敛为 503，
        # 不向外暴露凭证细节。
        logger.warning("聊天图片上传会话签名失败: %s", type(exc).__name__)
        raise APIError("chat_image_upload_unavailable", code=50396, status_code=503) from exc


def _real_image_mime(raw: bytes) -> str | None:
    """用 Pillow 验证字节可解码，并返回允许集合内的真实 MIME；校验失败返回 None。"""
    if not raw:
        return None
    try:
        with Image.open(BytesIO(raw)) as image:
            detected_format = image.format
            image.verify()
        # verify() 之后图像不可再用，重新打开做完整解码，拦截截断/损坏文件
        with Image.open(BytesIO(raw)) as image:
            image.load()
    except Exception:
        return None
    return _PIL_FORMAT_TO_MIME.get(detected_format or "")


def _new_session(*, user, mime_type: str, file_size: int, client_upload_id: str, thread_id: str = "") -> dict:
    object_key = f"{OBJECT_KEY_PREFIX}/{uuid.uuid4().hex}.{ALLOWED_IMAGE_MIME_EXT[mime_type]}"
    now = timezone.now()
    return {
        "session_id": uuid.uuid4().hex,
        "user_id": user.id,
        "object_key": object_key,
        "mime_type": mime_type,
        "file_size": file_size,
        "client_upload_id": client_upload_id,
        "thread_id": thread_id[:64],
        "status": "uploading",
        "file_id": None,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=SESSION_TTL_SECONDS)).isoformat(),
        "result": None,
    }


def _session_payload(session: dict, upload_url: str) -> dict:
    return {
        "upload_session_id": session["session_id"],
        "object_key": session["object_key"],
        "upload_url": upload_url,
        "upload_url_expires_in": UPLOAD_URL_EXPIRES_IN,
        "display_url": _display_url_for_key(session["object_key"]),
        "method": "PUT",
        "required_headers": {"Content-Type": session["mime_type"]},
        "max_file_size": MAX_IMAGE_FILE_SIZE,
        "expires_at": session["expires_at"],
    }


def _session_remaining_ttl(session: dict) -> int:
    expires_at = parse_datetime(str(session.get("expires_at") or ""))
    if expires_at is None:
        return 0
    return max(0, int((expires_at - timezone.now()).total_seconds()))


def _complete_result(file_record: ManagedFile) -> dict:
    return {
        "file_id": file_record.id,
        "file_uuid": str(file_record.file_uuid),
        "status": "ready",
        "display_url": managed_file_download_url(file_record),
        "version": file_record.updated_at.isoformat(),
    }


def _mark_session_ready(session: dict, file_record: ManagedFile, result: dict) -> None:
    session["status"] = "ready"
    session["file_id"] = file_record.id
    session["result"] = result
    remaining = _session_remaining_ttl(session)
    if remaining > 0:
        cache.set(_session_cache_key(session["session_id"]), session, timeout=remaining)


def _validate_session_request(data: dict) -> tuple[str, int, str]:
    purpose = str(data.get("purpose") or "chat_image")
    if purpose != "chat_image":
        raise APIError("chat_image_format_invalid", code=40100, status_code=400, details={"field": "purpose"})
    mime_type = str(data.get("mime_type") or "").strip().lower()
    if mime_type not in ALLOWED_IMAGE_MIME_EXT:
        raise APIError("chat_image_format_invalid", code=40100, status_code=400, details={"field": "mime_type"})
    try:
        file_size = int(data.get("file_size"))
    except (TypeError, ValueError):
        raise APIError("chat_image_format_invalid", code=40100, status_code=400, details={"field": "file_size"})
    if file_size < 1 or file_size > MAX_IMAGE_FILE_SIZE:
        raise APIError("chat_image_format_invalid", code=40100, status_code=400, details={"field": "file_size"})
    client_upload_id = data.get("client_upload_id")
    if (
        not isinstance(client_upload_id, str)
        or not client_upload_id.strip()
        or len(client_upload_id) > 128
        or any(ord(char) < 32 for char in client_upload_id)
    ):
        raise APIError("chat_image_format_invalid", code=40100, status_code=400, details={"field": "client_upload_id"})
    return mime_type, file_size, client_upload_id.strip()


class ChatImageUploadSessionView(APIView):
    """``POST /api/v1/oss/chat-images/upload-sessions/``：创建聊天图片上传会话。

    按 (user, client_upload_id) 幂等：重复请求返回同一会话（重签上传 URL）。
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatImageUploadThrottle]

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        mime_type, file_size, client_upload_id = _validate_session_request(data)

        intent_key = _intent_cache_key(request.user.id, client_upload_id)
        session = None
        existing_session_id = cache.get(intent_key)
        if existing_session_id:
            session = cache.get(_session_cache_key(str(existing_session_id)))
        replayed = session is not None
        if session is None:
            session = _new_session(
                user=request.user,
                mime_type=mime_type,
                file_size=file_size,
                client_upload_id=client_upload_id,
                thread_id=str(data.get("thread_id") or ""),
            )
            cache.set(_session_cache_key(session["session_id"]), session, timeout=SESSION_TTL_SECONDS)
            cache.set(intent_key, session["session_id"], timeout=SESSION_TTL_SECONDS)
            logger.info(
                "聊天图片上传会话创建 user_id=%s session_id=%s mime_type=%s file_size=%s",
                request.user.id,
                session["session_id"],
                mime_type,
                file_size,
            )
        upload_url = _sign_upload_url(object_key=session["object_key"], mime_type=session["mime_type"])
        return success_response(
            _session_payload(session, upload_url),
            msg="replayed" if replayed else "created",
            status_code=200 if replayed else 201,
        )


class ChatImageUploadSessionCompleteView(APIView):
    """``POST /api/v1/oss/chat-images/upload-sessions/<session_id>/complete/``：登记聊天图片。

    校验会话归属、object_key 一致性、OSS 对象真实存在、真实大小、MD5 与
    Pillow 解码结果，然后创建或复用 ManagedFile。重复提交返回同一 file_id。
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatImageUploadThrottle]

    def post(self, request, session_id):
        session = cache.get(_session_cache_key(str(session_id)))
        if session is None or session.get("user_id") != request.user.id:
            raise APIError("chat_image_not_found", code=40492, status_code=404)
        if session.get("status") == "ready" and session.get("file_id") and session.get("result"):
            return success_response(session["result"], msg="replayed", status_code=200)

        data = request.data if isinstance(request.data, dict) else {}
        object_key = str(data.get("object_key") or "")
        if str(data.get("client_upload_id") or "") != session["client_upload_id"] or object_key != session["object_key"]:
            raise APIError("chat_image_registration_failed", code=40202, status_code=400, details={"field": "object_key"})

        # 幂等复用：同一 object_key 已登记过则直接复用同一 file_id
        existing = ManagedFile.objects.filter(user=request.user, object_key=object_key, is_deleted=False).first()
        if existing is not None:
            result = _complete_result(existing)
            _mark_session_ready(session, existing, result)
            return success_response(result, msg="ready", status_code=200)

        start_time = time.perf_counter()

        # 1) 对象真实存在；以 head 返回的 Content-Length 为真实大小依据
        try:
            meta = object_meta(object_key=object_key)
        except OssUploadError as exc:
            raise APIError("chat_image_registration_failed", code=40202, status_code=400, details={"reason": str(exc)}) from exc

        # 2) 读取对象字节（上限 10 MB）
        try:
            raw = get_bytes(object_key=object_key, max_bytes=MAX_IMAGE_FILE_SIZE)
        except OssUploadError as exc:
            if str(exc) == "oss_object_too_large":
                raise APIError("chat_image_format_invalid", code=40100, status_code=400, details={"field": "file_size"}) from exc
            raise APIError("chat_image_registration_failed", code=40202, status_code=400, details={"reason": str(exc)}) from exc

        real_size = meta.content_length if meta.content_length is not None else len(raw)
        if real_size > MAX_IMAGE_FILE_SIZE:
            raise APIError("chat_image_format_invalid", code=40100, status_code=400, details={"field": "file_size"})
        declared_size = int(session.get("file_size") or 0)
        if declared_size and real_size != declared_size:
            raise APIError("chat_image_registration_failed", code=40202, status_code=400, details={"field": "file_size"})

        # 3) MD5 比对（客户端提供时）
        file_md5 = hashlib.md5(raw).hexdigest()
        claimed_md5 = str(data.get("file_md5") or "").strip().lower()
        if claimed_md5 and claimed_md5 != file_md5:
            raise APIError("chat_image_registration_failed", code=40202, status_code=400, details={"field": "file_md5"})

        # 4) 真实图片格式校验：可解码且与声明 MIME 一致
        real_mime = _real_image_mime(raw)
        if real_mime is None or real_mime != session["mime_type"]:
            raise APIError("chat_image_format_invalid", code=40100, status_code=400, details={"field": "mime_type"})

        # 5) 创建 ManagedFile（事实全部来自服务端校验结果）
        file_record = ManagedFile.objects.create(
            user=request.user,
            file_uuid=uuid.uuid4(),
            file_path="",
            original_name=object_key.rsplit("/", 1)[-1][:255],
            file_ext=ALLOWED_IMAGE_MIME_EXT[real_mime],
            mime_type=real_mime,
            file_size=real_size,
            file_md5=file_md5,
            is_public=True,
            object_key=object_key,
            storage_type="oss",
        )
        result = _complete_result(file_record)
        _mark_session_ready(session, file_record, result)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "聊天图片登记成功 user_id=%s session_id=%s file_id=%s mime_type=%s file_size=%s duration_ms=%s",
            request.user.id,
            session["session_id"],
            file_record.id,
            real_mime,
            real_size,
            duration_ms,
        )
        return success_response(result, msg="ready", status_code=201)
