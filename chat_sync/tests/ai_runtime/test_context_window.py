from chat_sync.ai_runtime.providers.context_window import (
    MAX_EFFECTIVE_CONTEXT_WINDOW,
    coerce_positive_int,
    resolve_effective_context_window,
)


def test_context_window_is_bounded_and_explicit_value_wins():
    assert coerce_positive_int(" 0 ") is None
    assert resolve_effective_context_window(context_window=2_000_000, model="custom", max_tokens=1) == MAX_EFFECTIVE_CONTEXT_WINDOW
    assert resolve_effective_context_window(context_window=32_768, model="custom", max_tokens=1) == 32_768

