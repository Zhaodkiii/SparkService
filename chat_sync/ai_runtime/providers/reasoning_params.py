"""Pure reasoning/thinking parameter compatibility rules."""

from __future__ import annotations

from typing import Any

_THINKING_STYLE_MAP = {
    "thinking_type": lambda enabled: {"thinking": {"type": "enabled" if enabled else "disabled"}},
    "enable_thinking": lambda enabled: {"enable_thinking": enabled},
    "reasoning_split": lambda enabled: {"reasoning_split": enabled},
}
_PROVIDER_THINKING_STYLES = {"deepseek": "thinking_type", "volcengine": "thinking_type", "volcengine_coding_plan": "thinking_type", "byteplus": "thinking_type", "byteplus_coding_plan": "thinking_type", "dashscope": "enable_thinking", "minimax": "reasoning_split"}
_PROVIDER_REASONING_PATTERNS = {"deepseek": ("deepseek-v4-pro", "deepseek-reasoner"), "dashscope": ("qwen3", "qwen-3", "qwq", "qwen-plus")}
_PROVIDER_DEFAULT_OFF_PATTERNS = {"gemini": ("gemini-2.5", "gemini-3")}
_CUSTOM_MODEL_THINKING_STYLES = ((("qwen3", "qwen-3", "qwq", "qwen-plus"), "enable_thinking"), (("deepseek-v4-pro", "deepseek-reasoner"), "thinking_type"))


def _matches(model_name: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern.lower() in model_name.lower() for pattern in patterns)


def _spec_name(spec: Any, binding: str | None) -> str:
    return str(getattr(spec, "name", None) or binding or "").strip().lower()


def default_reasoning_effort_for(provider: str | None, model: str | None) -> str | None:
    patterns = _PROVIDER_DEFAULT_OFF_PATTERNS.get((provider or "").strip().lower())
    return "none" if patterns and _matches(model or "", patterns) else None


def build_openai_compatible_reasoning_kwargs(*, spec: Any, binding: str | None, model: str | None, reasoning_effort: str | None) -> dict[str, Any]:
    provider = _spec_name(spec, binding)
    model_name = model or ""
    style = str(getattr(spec, "thinking_style", "") or "") or _PROVIDER_THINKING_STYLES.get(provider, "")
    patterns = tuple(getattr(spec, "reasoning_model_patterns", ()) or ()) or _PROVIDER_REASONING_PATTERNS.get(provider, ())
    if provider == "custom" and not style:
        for candidate_patterns, candidate_style in _CUSTOM_MODEL_THINKING_STYLES:
            if _matches(model_name, candidate_patterns):
                style, patterns = candidate_style, candidate_patterns
                break
    resolved = reasoning_effort
    if resolved is None:
        resolved = "high" if patterns and _matches(model_name, patterns) else default_reasoning_effort_for(provider, model_name)
    semantic = resolved.lower().replace("minimum", "minimal") if isinstance(resolved, str) else None
    kwargs: dict[str, Any] = {}
    if resolved and not (style and (semantic == "minimal" or style == "enable_thinking")):
        kwargs["reasoning_effort"] = resolved
    if style and resolved is not None:
        extra = _THINKING_STYLE_MAP.get(style, lambda _: None)(semantic != "minimal")
        if extra:
            kwargs.setdefault("extra_body", {}).update(extra)
    return kwargs


__all__ = ["build_openai_compatible_reasoning_kwargs", "default_reasoning_effort_for"]

