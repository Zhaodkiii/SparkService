from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chat_sync.ai_services.context.token_counter import count_message


@dataclass(frozen=True)
class HistorySelection:
    messages: tuple[dict[str, Any], ...]
    selected_ids: tuple[int, ...]
    trim_trace: tuple[dict[str, Any], ...]


def select_history(messages: list[dict[str, Any]], budget: int) -> HistorySelection:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "user" and current:
            groups.append(current)
            current = []
        if role in {"user", "assistant", "system"}:
            current.append(message)
    if current:
        groups.append(current)

    selected: list[dict[str, Any]] = []
    used = 0
    trace: list[dict[str, Any]] = []
    for group in reversed(groups):
        group_cost = sum(count_message(item).count for item in group)
        if selected and used + group_cost > budget:
            trace.append({"action": "drop_message_group", "message_ids": [item.get("id") for item in group], "tokens": group_cost})
            continue
        if not selected and group_cost > budget:
            # Keep the newest user message even when it is individually large;
            # the caller will raise if the non-trimmable current input is too big.
            trace.append({"action": "oversize_newest_group", "tokens": group_cost})
        selected[0:0] = group
        used += group_cost
    ids = tuple(int(item["id"]) for item in selected if item.get("id") is not None)
    return HistorySelection(tuple(selected), ids, tuple(trace))
