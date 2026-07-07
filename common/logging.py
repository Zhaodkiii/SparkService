import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from common.request_context import request_id_var


def _json_safe(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item) for item in value]
        return str(value)


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
                payload[key] = _json_safe(getattr(record, key))

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
                payload[key] = _json_safe(value)

        # Keep output clean for downstream tooling.
        payload = {k: v for k, v in payload.items() if v is not None}

        return json.dumps(payload, ensure_ascii=True)


class DateFolderTimedRotatingFileHandler(logging.FileHandler):
    """
    Rotate daily logs into LOG_ROOT/YYYY-MM-DD/<filename>.
    """

    def __init__(
        self,
        filename: str,
        log_root: str,
        when: str = "midnight",
        interval: int = 1,
        backupCount: int = 0,
        encoding: str | None = None,
        delay: bool = False,
        utc: bool = False,
        atTime=None,
    ):
        self.log_root = Path(log_root)
        self.base_filename = Path(filename).name
        self.use_utc_date = utc
        self.current_date = self._date_name()
        super().__init__(str(self._dated_filename()), mode="a", encoding=encoding, delay=delay)

    def _date_name(self) -> str:
        now = datetime.now(timezone.utc) if self.use_utc_date else datetime.now()
        return now.strftime("%Y-%m-%d")

    def _dated_filename(self) -> Path:
        log_dir = self.log_root / self.current_date
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / self.base_filename

    def _switch_date_if_needed(self) -> None:
        date_name = self._date_name()
        if date_name == self.current_date:
            return
        self.current_date = date_name
        self.baseFilename = os.fspath(self._dated_filename())
        if self.stream:
            self.stream.close()
            self.stream = None
        if not self.delay:
            self.stream = self._open()

    def emit(self, record: logging.LogRecord) -> None:
        self._switch_date_if_needed()
        super().emit(record)
