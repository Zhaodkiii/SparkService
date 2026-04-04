import json
import logging
from datetime import datetime, timezone

from common.request_context import request_id_var


class RequestIdFilter(logging.Filter):
    """
    Inject request_id from contextvars into every log record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """
    Render logs as compact JSON for ingestion by log systems.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "module_name": record.module,
            "file": record.filename,
            "function": record.funcName,
            "line": record.lineno,
            "pid": record.process,
            "thread": record.threadName,
        }

        # Keep useful optional attributes if present.
        for key in (
            "path",
            "method",
            "status_code",
            "duration_ms",
            "user_id",
            "client_ip",
            "user_agent",
            "response_bytes",
            "error_message",
            "task_id",
            "request_headers",
            "request_body",
            "response_headers",
            "response_body",
            "content_type",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        reserved = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "asctime",
            "request_id",
        }
        # Preserve any custom fields passed via `extra=...`.
        for key, value in record.__dict__.items():
            if key in reserved or key.startswith("_"):
                continue
            if value is None:
                continue
            if key not in payload:
                payload[key] = value

        # Keep output clean for downstream tooling.
        payload = {k: v for k, v in payload.items() if v is not None}

        return json.dumps(payload, ensure_ascii=True)
