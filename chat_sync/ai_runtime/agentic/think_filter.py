from __future__ import annotations

import re

_OPEN_THINK = "<think>"
_CLOSE_THINK = "</think>"


def _tag_prefix_len(text: str, tag: str) -> int:
    """How many trailing characters might still grow into ``tag``."""
    lower = text.lower()
    needle = tag.lower()
    max_n = min(len(needle) - 1, len(lower))
    for length in range(max_n, 0, -1):
        if needle.startswith(lower[-length:]):
            return length
    return 0


class InlineThinkFilter:
    """Remove inline think tags from provider output without persisting raw reasoning.

    Only a possible tag prefix is held back so short answers still stream in
    real time. Split tags such as ``<thi`` + ``nk>`` remain hidden until complete.
    """

    def __init__(self) -> None:
        self._inside = False
        self._buffer = ""

    def feed(self, text: str) -> str:
        self._buffer += text
        visible: list[str] = []
        while self._buffer:
            if self._inside:
                end = self._buffer.lower().find(_CLOSE_THINK)
                if end < 0:
                    keep = _tag_prefix_len(self._buffer, _CLOSE_THINK)
                    self._buffer = self._buffer[-keep:] if keep else ""
                    break
                self._buffer = self._buffer[end + len(_CLOSE_THINK):]
                self._inside = False
                continue
            start = self._buffer.lower().find(_OPEN_THINK)
            if start < 0:
                keep = _tag_prefix_len(self._buffer, _OPEN_THINK)
                if keep:
                    visible.append(self._buffer[:-keep])
                    self._buffer = self._buffer[-keep:]
                else:
                    visible.append(self._buffer)
                    self._buffer = ""
                break
            visible.append(self._buffer[:start])
            self._buffer = self._buffer[start + len(_OPEN_THINK):]
            self._inside = True
        return "".join(visible)

    def finish(self) -> str:
        if self._inside:
            self._buffer = ""
            return ""
        value = self._buffer
        self._buffer = ""
        return value


class ReasoningSafetyFilter:
    """Drop reasoning deltas that look like prompts, secrets, internal URLs or raw tool/health data.

    Conservative: if a delta cannot be shown safely, it is discarded. The final
    answer path is never blocked by this filter.
    """

    _UNSAFE = (
        re.compile(r"system prompt", re.I),
        re.compile(r"developer prompt", re.I),
        re.compile(r"\b(api[_-]?key|secret_key|authorization:|bearer\s+[a-z0-9._\-]{8,}|sk-[a-zA-Z0-9]{10,})\b", re.I),
        re.compile(r"https?://(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|[\w.-]+\.internal)(?:[:/]\S*)?", re.I),
        re.compile(r"\b(healthkit|身份证号?|社保号|member_id|patient_id)\b", re.I),
        re.compile(r"\"(?:arguments|tool_calls)\"\s*:"),
    )

    def __init__(self) -> None:
        self._tail = ""

    def feed(self, text: str) -> str:
        if not text:
            return ""
        window = f"{self._tail}{text}"
        if any(pattern.search(window) for pattern in self._UNSAFE):
            # Drop this delta only. Do not poison later safe deltas with the
            # rejected window, otherwise one leaky fragment would blank the rest
            # of the public summary.
            self._tail = ""
            return ""
        self._tail = window[-96:]
        return text
