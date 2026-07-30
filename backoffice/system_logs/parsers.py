import json
import re
from datetime import datetime


CONSOLE_RE = re.compile(
    r"^(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
    r"(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(?P<logger>[^\s]+)\s+"
    r"\[request_id=(?P<request_id>[^\]]+)\]\s+"
    r"(?P<message>.*)$"
)
STATUS_RE = re.compile(r"\bstatus(?:_code)?=(?P<status_code>\d{3})\b")
DURATION_RE = re.compile(r"\bduration_ms=(?P<duration_ms>\d+)\b")
METHOD_PATH_RE = re.compile(r"\b(?P<method>GET|POST|PUT|PATCH|DELETE|OPTIONS)\s+(?P<path>/[^\s]+)")
ERROR_CODE_RE = re.compile(r'"code"\s*:\s*(?P<error_code>\d+)')
ERROR_MSG_RE = re.compile(r'"msg"\s*:\s*"(?P<error_message>[^"]+)"')


def parse_console_line(line: str) -> dict:
    raw = line.rstrip("\n")
    if not raw:
        return {"parse_status": "empty", "raw": raw}

    match = CONSOLE_RE.match(raw)
    if not match:
        return {"parse_status": "unparsed", "message": raw, "raw": raw}

    row = match.groupdict()
    message = row["message"]
    row["timestamp"] = datetime.strptime(row.pop("ts"), "%Y-%m-%d %H:%M:%S,%f").isoformat()
    row["parse_status"] = "parsed"
    row["raw"] = raw

    for regex, key, caster in (
        (STATUS_RE, "status_code", int),
        (DURATION_RE, "duration_ms", int),
        (ERROR_CODE_RE, "error_code", int),
        (ERROR_MSG_RE, "error_message", str),
    ):
        found = regex.search(message)
        if found:
            row[key] = caster(found.group(key))

    method_path = METHOD_PATH_RE.search(message)
    if method_path:
        row["method"] = method_path.group("method")
        row["path"] = method_path.group("path")

    return row


def parse_log_line(line: str) -> dict:
    raw = line.rstrip("\n")
    if not raw:
        return {"parse_status": "empty", "raw": raw}

    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            pass
        else:
            return {
                "parse_status": "parsed",
                "timestamp": payload.get("ts"),
                "level": payload.get("level"),
                "logger": payload.get("logger"),
                "request_id": payload.get("request_id"),
                "method": payload.get("method"),
                "path": payload.get("path"),
                "status_code": payload.get("status_code"),
                "duration_ms": payload.get("duration_ms"),
                "error_message": payload.get("error_message"),
                "message": payload.get("message") or "",
                "raw": payload,
            }

    return parse_console_line(raw)


def match_status(row: dict, status: str) -> bool:
    if not status:
        return True

    code = row.get("status_code")
    level = (row.get("level") or "").upper()
    message = row.get("message") or ""

    if status.endswith("xx") and len(status) == 3 and status[0].isdigit():
        if code is None:
            return False
        start = int(status[0]) * 100
        return start <= int(code) < start + 100
    if status.isdigit():
        return int(code or 0) == int(status)
    if status == "failed":
        return level in {"WARNING", "ERROR", "CRITICAL"} or "failed" in message.lower() or "失败" in message
    return True
