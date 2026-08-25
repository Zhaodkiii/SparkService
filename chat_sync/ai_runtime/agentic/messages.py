"""Canonical message builders for tool-call transcripts."""

from __future__ import annotations

from typing import Any
import json


def assistant_message_with_tool_calls(
    content: str | None,
    tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": content or None,
        "tool_calls": [
            {
                "id": call["id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call.get("arguments") or {}, ensure_ascii=False, separators=(",", ":")) if isinstance(call.get("arguments"), (dict, list)) else (call.get("arguments") or "{}"),
                },
            }
            for call in tool_calls
        ],
    }


__all__ = ["assistant_message_with_tool_calls"]
