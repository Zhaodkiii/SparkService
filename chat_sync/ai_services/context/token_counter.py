from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenCount:
    count: int
    method: str
    estimated: bool
    version: str = "1"


_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


def count_tokens(value: Any) -> TokenCount:
    text = value if isinstance(value, str) else _canonical_text(value)
    if not text:
        return TokenCount(0, "empty", False)
    try:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        return TokenCount(len(encoding.encode(text)), "cl100k_base", False, getattr(tiktoken, "__version__", "unknown"))
    except Exception:
        cjk = len(_CJK.findall(text))
        other = max(0, len(text) - cjk)
        # Conservative for Chinese and JSON-heavy prompts; the result is a
        # planning bound, not a billing claim.
        estimate = max(1, math.ceil(cjk * 1.3 + other / 3.6))
        return TokenCount(estimate, "heuristic", True)


def count_message(message: dict[str, Any]) -> TokenCount:
    content = message.get("content", "")
    value = content if isinstance(content, str) else _canonical_text(content)
    base = count_tokens(value)
    overhead = 4
    return TokenCount(base.count + overhead, base.method, base.estimated, base.version)


def _canonical_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
