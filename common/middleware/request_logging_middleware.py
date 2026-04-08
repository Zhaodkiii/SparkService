import logging
import time
import json
import os


logger = logging.getLogger("accounts.request")
io_logger = logging.getLogger("accounts.api_io")
medical_io_logger = logging.getLogger("medical.api_io")
API_IO_ENABLED = os.getenv("LOG_API_IO_ENABLED", "true").lower() in ("1", "true", "yes", "y")


def _api_io_max_body_len() -> int | None:
    """
    None = log full body/headers string. Set LOG_API_IO_MAX_BODY_LEN=1024 to restore old truncation.
    """
    raw = os.getenv("LOG_API_IO_MAX_BODY_LEN")
    if raw is None:
        return None
    s = raw.strip().lower()
    if s in ("", "0", "full", "none", "unlimited", "off", "false", "no"):
        return None
    try:
        n = int(s)
        return None if n <= 0 else n
    except ValueError:
        return None


_LOG_IO_MAX_BODY_LEN: int | None = _api_io_max_body_len()


def _short_repr(obj, max_len: int | None = None) -> str:
    """
    将请求/响应头和报文压缩为单行字符串；默认完整输出，可通过 LOG_API_IO_MAX_BODY_LEN 限制长度。
    """
    limit = max_len if max_len is not None else _LOG_IO_MAX_BODY_LEN
    try:
        if isinstance(obj, (dict, list)):
            text = json.dumps(obj, ensure_ascii=False)
        else:
            text = str(obj)
    except Exception:
        text = repr(obj)
    if limit is not None and len(text) > limit:
        return text[: limit - 20] + "...(truncated)"
    return text

def _headers_for_log(headers: dict | None) -> dict:
    if not headers:
        return {}
    return {str(k): str(v) for k, v in headers.items()}


def _log_level_by_status(status_code: int):
    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO


def _safe_decode_bytes(raw: bytes | None) -> str:
    if not raw:
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return f"<binary:{len(raw)} bytes>"


def _body_for_log(raw: bytes | None, content_type: str | None = None):
    text = _safe_decode_bytes(raw)
    if not text:
        return ""

    content_type = (content_type or "").lower()
    if "application/json" in content_type:
        try:
            return json.loads(text)
        except Exception:
            return text
    return text


class RequestLoggingMiddleware:
    """
    Emit one structured access log per request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        request_io_logger = self._io_logger_for_path(request.path)
        request_headers = _headers_for_log(dict(request.headers))
        request_body = _body_for_log(request.body, request.content_type)
        user_id = None
        client_ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")) or ""
        user_agent = request.META.get("HTTP_USER_AGENT", "") or ""
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            user_id = user.id

        if API_IO_ENABLED:
            request_io_logger.info(
                "HTTP 请求进入: %s %s headers=%s body=%s"
                % (
                    request.method,
                    request.path,
                    _short_repr(request_headers),
                    _short_repr(request_body),
                ),
                extra={
                    "path": request.path,
                    "method": request.method,
                    "user_id": user_id,
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "content_type": request.content_type or "",
                    "request_headers": request_headers,
                    "request_body": request_body,
                },
            )
        try:
            response = self.get_response(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.exception(
                "HTTP 请求处理异常: %s %s"
                % (
                    request.method,
                    request.path,
                ),
                extra={
                    "path": request.path,
                    "method": request.method,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                },
            )
            if API_IO_ENABLED:
                request_io_logger.exception(
                    "HTTP 响应发送异常: %s %s headers=%s body=%s"
                    % (
                        request.method,
                        request.path,
                        _short_repr(request_headers),
                        _short_repr(request_body),
                    ),
                    extra={
                        "path": request.path,
                        "method": request.method,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                        "user_id": user_id,
                        "client_ip": client_ip,
                        "user_agent": user_agent,
                        "request_headers": request_headers,
                        "request_body": request_body,
                    },
                )
            raise

        duration_ms = int((time.perf_counter() - start) * 1000)

        response_headers = _headers_for_log(dict(response.headers))
        response_content_type = response_headers.get("Content-Type", "")
        response_body = ""
        response_bytes = 0
        if hasattr(response, "streaming") and not getattr(response, "streaming", False):
            response_content = getattr(response, "content", b"")
            response_body = _body_for_log(response_content, response_content_type)
            response_bytes = len(response_content or b"")

        summary_level = _log_level_by_status(status_code)
        logger.log(
            summary_level,
            "HTTP 请求摘要: %s %s status=%s duration_ms=%s bytes=%s"
            % (
                request.method,
                request.path,
                status_code,
                duration_ms,
                response_bytes,
            ),
            extra={
                "path": request.path,
                "method": request.method,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "user_id": user_id,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "response_bytes": response_bytes,
            },
        )
        if API_IO_ENABLED:
            response_msg = (
                "HTTP 响应摘要: %s %s status=%s duration_ms=%s bytes=%s headers=%s body=%s"
                % (
                    request.method,
                    request.path,
                    status_code,
                    duration_ms,
                    response_bytes,
                    _short_repr(response_headers),
                    _short_repr(response_body),
                )
            )
            response_extra = {
                "path": request.path,
                "method": request.method,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "user_id": user_id,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "response_bytes": response_bytes,
                "response_headers": response_headers,
                "response_body": response_body,
            }
            if status_code >= 400:
                response_msg += " request_body=%s" % (_short_repr(request_body),)
                response_extra["request_body"] = request_body
            request_io_logger.log(summary_level, response_msg, extra=response_extra)
        return response

    @staticmethod
    def _io_logger_for_path(path: str):
        if path.startswith("/api/v1/medical/"):
            return medical_io_logger
        return io_logger
