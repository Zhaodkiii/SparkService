from __future__ import annotations

from typing import Any


def summarize_messages(messages: list[dict[str, Any]], max_chars: int = 3000) -> tuple[str, dict[str, Any]]:
    """Deterministic, auditable fallback summary.

    A configured context_folding provider can replace this function later. The
    fallback never invents facts and keeps role/date/number text verbatim.
    """
    lines: list[str] = []
    used = 0
    for item in messages:
        text = str(item.get("content") or "").strip()
        if not text:
            continue
        role = "用户" if item.get("role") == "user" else "助手"
        line = f"{role}：{text}"
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(line) > remaining:
            line = line[:remaining].rstrip() + "…"
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines), {"action": "deterministic_summary", "source_message_count": len(messages), "chars": used}
