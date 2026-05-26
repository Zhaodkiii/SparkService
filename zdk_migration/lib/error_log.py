"""Deduplicated migration error/warning log for post-run review."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from django.conf import settings

_ID_PATTERNS = (
    (re.compile(r"\b(old_patient_id|old_id|user_id|record_id|patient_id|member_id|target_id)=\S+"), r"\1={id}"),
    (re.compile(r"\bid=\d+\b"), "id={id}"),
    (re.compile(r":\d+\b"), ":{id}"),
    (re.compile(r"\bold_id=\d+\b"), "old_id={id}"),
)


@dataclass
class _IssueBucket:
    count: int = 0
    samples: list[str] = field(default_factory=list)


_buckets: dict[tuple[str, str, str], _IssueBucket] = {}


def error_log_path() -> Path:
    return Path(settings.BASE_DIR) / "scripts" / "migration" / "state" / "errors.log"


def normalize_reason(message: str) -> str:
    """Collapse row-specific details so identical failures group together."""
    text = (message or "").strip()
    if text.startswith("stale ") and " map cleared " in text:
        return re.sub(
            r"old_id=\S+ (missing|missing_or_mismatched) target_id=\S+",
            r"old_id={id} \1 target_id={id}",
            text,
        )
    if text.startswith("fail:"):
        body = text[5:].strip()
        if " (" in body:
            label, exc = body.rsplit(" (", 1)
            exc = exc.rstrip(")")
            return f"fail: {_strip_ids(label)} ({exc})"
        return f"fail: {_strip_ids(body)}"
    if text.startswith("skip:"):
        return f"skip: {_strip_ids(text[5:].strip())}"
    return _strip_ids(text)


def _strip_ids(text: str) -> str:
    result = text
    for pattern, repl in _ID_PATTERNS:
        result = pattern.sub(repl, result)
    return result


def record_migration_issue(command: str, level: str, message: str, *, sample_limit: int = 3) -> None:
    reason = normalize_reason(message) if level in {"FAIL", "SKIP", "WARN"} else message
    key = (command, level, reason)
    bucket = _buckets.setdefault(key, _IssueBucket())
    bucket.count += 1
    if len(bucket.samples) < sample_limit:
        bucket.samples.append(message[:240])


def flush_migration_issues(command: str | None = None) -> None:
    path = error_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")
    keys = [k for k in _buckets if command is None or k[0] == command]
    if not keys:
        return
    with path.open("a", encoding="utf-8") as fh:
        for cmd, level, reason in sorted(keys):
            bucket = _buckets[(cmd, level, reason)]
            suffix = "SUMMARY" if level in {"FAIL", "SKIP", "WARN"} else level
            line = f"[{ts}] [{suffix}] [{cmd}] count={bucket.count} {reason}"
            if bucket.samples:
                samples = ", ".join(bucket.samples)
                extra = bucket.count - len(bucket.samples)
                if extra > 0:
                    samples = f"{samples} (+{extra} more)"
                line += f" | samples: {samples}"
            fh.write(line + "\n")
    for key in keys:
        _buckets.pop(key, None)


def reset_migration_issues(command: str | None = None) -> None:
    if command is None:
        _buckets.clear()
        return
    for key in [k for k in _buckets if k[0] == command]:
        _buckets.pop(key, None)


def clear_error_log() -> None:
    path = error_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    _buckets.clear()


def append_error_log(command: str, level: str, message: str) -> None:
    """Backward-compatible entry point; records deduplicated issues."""
    record_migration_issue(command, level, message)
