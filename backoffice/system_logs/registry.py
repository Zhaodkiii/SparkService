import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from common.exceptions import APIError


@dataclass(frozen=True)
class LogModule:
    value: str
    label: str
    filename: str
    default_status_field: str = "status_code"


LOG_MODULES: dict[str, LogModule] = {
    "access": LogModule("access", "请求摘要", "access.log"),
    "accounts_api_io": LogModule("accounts_api_io", "账号 API IO", "access_api_io.log"),
    "app": LogModule("app", "应用日志", "app.log"),
    "celery": LogModule("celery", "Celery", "celery.log"),
    "chat_sync": LogModule("chat_sync", "对话同步", "chat_sync.log"),
    "chat_sync_api_io": LogModule("chat_sync_api_io", "对话 API IO", "chat_sync_api_io.log"),
    "medical_flow": LogModule("medical_flow", "医疗数据流程", "medical_flow.log"),
    "medical_api_io": LogModule("medical_api_io", "医疗 API IO", "medical_api_io.log"),
    "nutrition_api_io": LogModule("nutrition_api_io", "营养 API IO", "nutrition_api_io.log"),
    "file_manager": LogModule("file_manager", "文件管理", "file_manager.log"),
    "notification_center": LogModule("notification_center", "通知中心", "notification_center.log"),
}

MAX_FILE_BYTES = 100 * 1024 * 1024
LOG_DATE_PATTERN = "YYYY-MM-DD"


def get_log_root() -> Path:
    return Path(settings.LOG_ROOT).resolve()


def get_log_host_path_hint() -> str:
    return getattr(settings, "LOG_HOST_PATH_HINT", "") or ""


def build_log_context(*, date: str = "", module: str = "") -> dict:
    root = get_log_root()
    context = {
        "log_root": str(root),
        "date_pattern": LOG_DATE_PATTERN,
        "host_path_hint": get_log_host_path_hint(),
    }
    if date:
        context["date"] = date
    if date and module in LOG_MODULES:
        filename = LOG_MODULES[module].filename
        context["file"] = filename
        context["log_file"] = str(root / date / filename)
        host_hint = get_log_host_path_hint()
        if host_hint:
            context["host_log_file"] = f"{host_hint.rstrip('/')}/{date}/{filename}"
    return context


def resolve_log_file(*, date: str, module: str) -> Path:
    if module not in LOG_MODULES:
        raise APIError("invalid_log_module", code=40071, status_code=400)

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise APIError("invalid_log_date", code=40072, status_code=400)

    root = get_log_root()
    path = (root / date / LOG_MODULES[module].filename).resolve()
    if root != path and root not in path.parents:
        raise APIError("invalid_log_path", code=40073, status_code=400)
    return path


def list_available_dates() -> list[str]:
    root = get_log_root()
    if not root.exists():
        return []
    dates = []
    for child in root.iterdir():
        if child.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", child.name):
            dates.append(child.name)
    return sorted(dates, reverse=True)


def list_module_dates(module: str) -> list[str]:
    if module not in LOG_MODULES:
        return []
    filename = LOG_MODULES[module].filename
    root = get_log_root()
    if not root.exists():
        return []
    dates = []
    for child in root.iterdir():
        if child.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", child.name):
            if (child / filename).exists():
                dates.append(child.name)
    return sorted(dates, reverse=True)
