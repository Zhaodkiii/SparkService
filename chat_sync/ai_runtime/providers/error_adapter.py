from __future__ import annotations

from dataclasses import dataclass

from .exceptions import LLMAuthenticationError, LLMError, LLMRateLimitError, LLMTimeoutError


@dataclass(frozen=True)
class RunError:
    code: str
    message: str
    retryable: bool


def adapt_error(exc: Exception) -> RunError:
    if isinstance(exc, LLMAuthenticationError):
        return RunError("provider_auth_failed", "模型服务鉴权失败", False)
    if isinstance(exc, LLMRateLimitError):
        return RunError("provider_rate_limited", "模型服务请求受限", True)
    if isinstance(exc, LLMTimeoutError):
        return RunError("provider_timeout", "模型服务响应超时", True)
    if isinstance(exc, LLMError):
        return RunError("provider_error", "模型服务暂时不可用", True)
    return RunError("provider_unavailable", "模型服务暂时不可用", True)

