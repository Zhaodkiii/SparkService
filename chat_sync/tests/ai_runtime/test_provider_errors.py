from chat_sync.ai_runtime.providers.error_mapping import map_error
from chat_sync.ai_runtime.providers.exceptions import LLMAuthenticationError, LLMRateLimitError, ProviderContextWindowError


class AuthenticationError(Exception):
    pass


class RateLimitError(Exception):
    pass


def test_error_mapping_does_not_import_provider_sdk_types():
    assert isinstance(map_error(AuthenticationError("bad"), provider="ark"), LLMAuthenticationError)
    assert isinstance(map_error(RateLimitError("rate limit"), provider="ark"), LLMRateLimitError)
    assert isinstance(map_error(Exception("maximum context exceeded")), ProviderContextWindowError)


def test_status_code_mapping_is_stable():
    error = map_error(type("ProviderError", (), {"status_code": 429})(), provider="openai")
    assert isinstance(error, LLMRateLimitError)
    assert error.status_code == 429

