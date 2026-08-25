"""Provider exception classification without importing optional SDKs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .exceptions import LLMAPIError, LLMAuthenticationError, LLMError, LLMRateLimitError, ProviderContextWindowError

ErrorClassifier = Callable[[Exception], bool]


@dataclass(frozen=True)
class MappingRule:
    classifier: ErrorClassifier
    factory: Callable[[Exception, str | None], LLMError]


def _message_contains(*needles: str) -> ErrorClassifier:
    return lambda exc: any(needle in str(exc).lower() for needle in needles)


def _class_named(*names: str) -> ErrorClassifier:
    expected = set(names)
    return lambda exc: any(cls.__name__ in expected for cls in type(exc).__mro__)


_GLOBAL_RULES = [
    MappingRule(_class_named("AuthenticationError", "AuthenticationStatusError"), lambda exc, p: LLMAuthenticationError(str(exc), provider=p)),
    MappingRule(_class_named("RateLimitError"), lambda exc, p: LLMRateLimitError(str(exc), provider=p)),
    MappingRule(_message_contains("rate limit", "429", "quota"), lambda exc, p: LLMRateLimitError(str(exc), provider=p)),
    MappingRule(_message_contains("context length", "maximum context"), lambda exc, p: ProviderContextWindowError(str(exc), provider=p)),
]


def map_error(exc: Exception, provider: str | None = None) -> LLMError:
    status_code = getattr(exc, "status_code", None)
    if status_code == 401:
        return LLMAuthenticationError(str(exc), provider=provider)
    if status_code == 429:
        return LLMRateLimitError(str(exc), provider=provider)
    for rule in _GLOBAL_RULES:
        if rule.classifier(exc):
            return rule.factory(exc, provider)
    return LLMAPIError(str(exc), status_code=status_code, provider=provider)


__all__ = ["MappingRule", "map_error"]

