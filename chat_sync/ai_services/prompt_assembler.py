from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptBlock:
    name: str
    content: str
    priority: int
    trim_eligible: bool = True


PROMPT_VERSION = "chat.prompt.v1"


def assemble_messages(*, blocks: list[PromptBlock], history: list[dict[str, Any]], current_text: str | list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[PromptBlock]]:
    # current_text 支持纯字符串或多模态 content parts（text + image_url），
    # 后者由 OpenAI 兼容网关原样转发。
    ordered = sorted((item for item in blocks if item.content.strip()), key=lambda item: item.priority)
    system = "\n\n---\n\n".join(f"## {item.name}\n{_escape(item.content)}" for item in ordered)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for item in history:
        if item.get("role") in {"user", "assistant"} and str(item.get("content") or "").strip():
            messages.append({"role": str(item["role"]), "content": str(item["content"])})
    messages.append({"role": "user", "content": current_text})
    return messages, ordered


def _escape(value: str) -> str:
    return value.replace("</source>", "&lt;/source&gt;").replace("<system>", "&lt;system&gt;")
