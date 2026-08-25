from __future__ import annotations


class InlineThinkFilter:
    """Remove inline think tags from provider output without persisting raw reasoning."""

    def __init__(self) -> None:
        self._inside = False
        self._buffer = ""

    def feed(self, text: str) -> str:
        self._buffer += text
        visible: list[str] = []
        while self._buffer:
            if self._inside:
                end = self._buffer.lower().find("</think>")
                if end < 0:
                    self._buffer = self._buffer[-8:]
                    break
                self._buffer = self._buffer[end + len("</think>"):]
                self._inside = False
                continue
            start = self._buffer.lower().find("<think>")
            if start < 0:
                if len(self._buffer) > 8:
                    visible.append(self._buffer[:-8])
                    self._buffer = self._buffer[-8:]
                break
            visible.append(self._buffer[:start])
            self._buffer = self._buffer[start + len("<think>"):]
            self._inside = True
        return "".join(visible)

    def finish(self) -> str:
        if self._inside:
            self._buffer = ""
            return ""
        value = self._buffer
        self._buffer = ""
        return value

