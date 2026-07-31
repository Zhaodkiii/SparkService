from dataclasses import dataclass

from common.exceptions import APIError

from .exposure import expose_log_value, raw_preview
from .parsers import match_status, parse_log_line
from .registry import LOG_MODULES, MAX_FILE_BYTES, build_log_context, list_module_dates, resolve_log_file


MAX_SCAN_LINES = 200_000
MAX_PAGE_SIZE = 200


@dataclass
class SystemLogQuery:
    date: str
    module: str
    level: str = ""
    status: str = ""
    request_id: str = ""
    path: str = ""
    keyword: str = ""
    page: int = 1
    page_size: int = 50
    order: str = "desc"


class SystemLogService:
    @staticmethod
    def list_modules() -> dict:
        items = []
        for item in LOG_MODULES.values():
            items.append(
                {
                    "value": item.value,
                    "label": item.label,
                    "file": item.filename,
                    "available_dates": list_module_dates(item.value),
                }
            )
        return {
            **build_log_context(),
            "items": items,
        }

    @staticmethod
    def query(query: SystemLogQuery) -> dict:
        path = resolve_log_file(date=query.date, module=query.module)
        page_size = min(max(query.page_size, 1), MAX_PAGE_SIZE)
        page = max(query.page, 1)

        if not path.exists():
            return {
                "items": [],
                "pagination": {"page": page, "page_size": page_size, "total": 0, "total_pages": 0},
                "scan_limited": False,
                "context": {
                    **build_log_context(date=query.date, module=query.module),
                    "file_exists": False,
                },
            }

        if path.stat().st_size > MAX_FILE_BYTES:
            raise APIError("log_file_too_large", code=40074, status_code=400)

        rows = []
        scan_limited = False
        with path.open("r", encoding="utf-8", errors="replace") as fp:
            for line_no, line in enumerate(fp, start=1):
                if line_no > MAX_SCAN_LINES:
                    scan_limited = True
                    break
                row = parse_log_line(line)
                if row.get("parse_status") == "empty":
                    continue
                row.update(
                    {
                        "line_no": line_no,
                        "date": query.date,
                        "module": query.module,
                        "file": path.name,
                    }
                )
                if not SystemLogService._match(row, query):
                    continue
                rows.append(row)

        if query.order == "desc":
            rows.reverse()

        total = len(rows)
        start = (page - 1) * page_size
        end = start + page_size
        page_rows = rows[start:end]

        return {
            "items": [SystemLogService._serialize_list_item(row) for row in page_rows],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size if total else 0,
            },
            "scan_limited": scan_limited,
            "context": {
                **build_log_context(date=query.date, module=query.module),
                "file_exists": True,
            },
        }

    @staticmethod
    def detail(*, date: str, module: str, line_no: int) -> dict:
        path = resolve_log_file(date=date, module=module)
        if not path.exists():
            raise APIError("log_file_not_found", code=40471, status_code=404)
        if line_no < 1:
            raise APIError("invalid_line_no", code=40075, status_code=400)

        with path.open("r", encoding="utf-8", errors="replace") as fp:
            for current, line in enumerate(fp, start=1):
                if current == line_no:
                    row = parse_log_line(line)
                    return SystemLogService._serialize_detail(row, date=date, module=module, line_no=line_no, file=path.name)
        raise APIError("log_line_not_found", code=40472, status_code=404)

    @staticmethod
    def _match(row: dict, query: SystemLogQuery) -> bool:
        if query.level and (row.get("level") or "").upper() != query.level.upper():
            return False
        if query.request_id and row.get("request_id") != query.request_id:
            return False
        if query.path:
            path_value = row.get("path") or ""
            message = row.get("message") or ""
            if query.path not in path_value and query.path not in message:
                return False
        if query.keyword:
            haystack = str(row.get("raw", "")).lower()
            if query.keyword.lower() not in haystack:
                return False
        return match_status(row, query.status)

    @staticmethod
    def _serialize_list_item(row: dict) -> dict:
        date = row.get("date", "")
        module = row.get("module", "")
        line_no = row.get("line_no", 0)
        raw = row.get("raw", "")
        return {
            "id": f"{date}:{module}:{line_no}",
            "date": date,
            "module": module,
            "file": row.get("file", ""),
            "line_no": line_no,
            "timestamp": row.get("timestamp"),
            "level": row.get("level") or "",
            "logger": row.get("logger") or "",
            "request_id": row.get("request_id") or "",
            "method": row.get("method"),
            "path": row.get("path"),
            "status_code": row.get("status_code"),
            "duration_ms": row.get("duration_ms"),
            "error_code": row.get("error_code"),
            "error_message": row.get("error_message"),
            "message": row.get("message") or "",
            "raw_preview": raw_preview(raw),
        }

    @staticmethod
    def _serialize_detail(row: dict, *, date: str, module: str, line_no: int, file: str) -> dict:
        raw = row.get("raw", "")
        raw_text = raw if isinstance(raw, str) else str(raw)
        parsed = expose_log_value(
            {
                "level": row.get("level"),
                "timestamp": row.get("timestamp"),
                "logger": row.get("logger"),
                "request_id": row.get("request_id"),
                "method": row.get("method"),
                "path": row.get("path"),
                "status_code": row.get("status_code"),
                "duration_ms": row.get("duration_ms"),
                "error_code": row.get("error_code"),
                "error_message": row.get("error_message"),
                "message": row.get("message"),
                "parse_status": row.get("parse_status"),
            }
        )
        if isinstance(raw, dict):
            parsed.update(expose_log_value(raw))

        request_id = row.get("request_id") or ""
        return {
            "date": date,
            "module": module,
            "file": file,
            "line_no": line_no,
            "parsed": parsed,
            "raw": raw_text if isinstance(raw, str) else expose_log_value(raw),
            "related_query": {"request_id": request_id} if request_id else {},
        }
