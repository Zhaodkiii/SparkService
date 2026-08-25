"""Validation and normalization for the future ``ask_user`` tool payload."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_QUESTIONS = 4
MAX_OPTIONS = 8
MAX_OPTION_CHARS = 120
MAX_OPTION_DESC_CHARS = 200
MAX_HEADER_CHARS = 16
MAX_QUESTION_CHARS = 800
MAX_INTRO_CHARS = 400
MAX_PLACEHOLDER_CHARS = 120
_REDUNDANT_OTHER_LABELS = {"other", "others", "其他", "其它"}


@dataclass(frozen=True)
class AskUserOption:
    label: str
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "description": self.description}


@dataclass(frozen=True)
class AskUserQuestion:
    id: str
    prompt: str
    options: tuple[AskUserOption, ...] = ()
    header: str | None = None
    multi_select: bool = False
    allow_free_text: bool = True
    placeholder: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "prompt": self.prompt, "options": [o.to_dict() for o in self.options], "header": self.header, "multi_select": self.multi_select, "allow_free_text": self.allow_free_text, "placeholder": self.placeholder}


@dataclass(frozen=True)
class AskUserPayload:
    questions: tuple[AskUserQuestion, ...]
    intro: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"intro": self.intro, "questions": [q.to_dict() for q in self.questions]}

    @property
    def question_ids(self) -> tuple[str, ...]:
        return tuple(q.id for q in self.questions)


def _text(value: Any) -> str:
    return "" if value is None else value if isinstance(value, str) else str(value)


def _option(raw: Any) -> AskUserOption | None:
    if isinstance(raw, dict):
        label, description = _text(raw.get("label")).strip(), _text(raw.get("description")).strip() or None
    else:
        label, description = _text(raw).strip(), None
    if not label:
        return None
    if len(label) > MAX_OPTION_CHARS:
        label = label[:MAX_OPTION_CHARS].rstrip() + "…"
    if description and len(description) > MAX_OPTION_DESC_CHARS:
        description = description[:MAX_OPTION_DESC_CHARS].rstrip() + "…"
    return AskUserOption(label, description)


def build_ask_user_payload(*, questions: Any = None, intro: Any = None, question: Any = None, options: Any = None) -> tuple[AskUserPayload | None, str | None]:
    if questions is not None:
        if not isinstance(questions, (list, tuple)):
            return None, "`questions` must be an array."
        raw_questions = list(questions)
    elif question is not None:
        raw_questions = [{"prompt": question, "options": options}]
    else:
        raw_questions = []
    if not raw_questions:
        return None, "`questions` must contain at least one question."
    normalized: list[AskUserQuestion] = []
    used_ids: set[str] = set()
    for index, raw in enumerate(raw_questions[:MAX_QUESTIONS]):
        if not isinstance(raw, dict):
            return None, f"Question #{index + 1} must be an object."
        prompt = _text(raw.get("prompt", raw.get("question"))).strip()
        if not prompt:
            return None, f"Question #{index + 1}: `prompt` must be a non-empty string."
        if len(prompt) > MAX_QUESTION_CHARS:
            prompt = prompt[:MAX_QUESTION_CHARS].rstrip() + "…"
        free_text = True if raw.get("allow_free_text") is None else bool(raw.get("allow_free_text"))
        raw_options = raw.get("options")
        if raw_options is not None and not isinstance(raw_options, (list, tuple)):
            return None, f"Question #{index + 1}: `options` must be an array."
        clean_options: list[AskUserOption] = []
        labels: set[str] = set()
        for raw_option in raw_options or []:
            item = _option(raw_option)
            if not item or (free_text and item.label.lower() in _REDUNDANT_OTHER_LABELS) or item.label in labels:
                continue
            labels.add(item.label)
            clean_options.append(item)
            if len(clean_options) == MAX_OPTIONS:
                break
        header = _text(raw.get("header")).strip() or None
        placeholder = _text(raw.get("placeholder")).strip() or None
        if header and len(header) > MAX_HEADER_CHARS:
            header = header[:MAX_HEADER_CHARS].rstrip()
        if placeholder and len(placeholder) > MAX_PLACEHOLDER_CHARS:
            placeholder = placeholder[:MAX_PLACEHOLDER_CHARS].rstrip() + "…"
        qid = _text(raw.get("id")).strip() or f"q{index + 1}"
        if qid in used_ids:
            suffix = 2
            while f"{qid}_{suffix}" in used_ids:
                suffix += 1
            qid = f"{qid}_{suffix}"
        used_ids.add(qid)
        normalized.append(AskUserQuestion(qid, prompt, tuple(clean_options), header, bool(raw.get("multi_select", raw.get("multiSelect", False))), free_text, placeholder))
    intro_text = _text(intro).strip() or None
    if intro_text and len(intro_text) > MAX_INTRO_CHARS:
        intro_text = intro_text[:MAX_INTRO_CHARS].rstrip() + "…"
    return AskUserPayload(tuple(normalized), intro_text), None


__all__ = ["AskUserOption", "AskUserPayload", "AskUserQuestion", "MAX_QUESTIONS", "MAX_OPTIONS", "MAX_OPTION_CHARS", "MAX_OPTION_DESC_CHARS", "MAX_HEADER_CHARS", "MAX_QUESTION_CHARS", "MAX_INTRO_CHARS", "MAX_PLACEHOLDER_CHARS", "build_ask_user_payload"]

