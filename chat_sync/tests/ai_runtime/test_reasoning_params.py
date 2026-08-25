from types import SimpleNamespace

from chat_sync.ai_runtime.providers.reasoning_params import build_openai_compatible_reasoning_kwargs


def test_volcengine_reasoning_uses_extra_body():
    result = build_openai_compatible_reasoning_kwargs(
        spec=SimpleNamespace(name="volcengine"), binding=None, model="doubao-seed", reasoning_effort="high"
    )
    assert result["extra_body"] == {"thinking": {"type": "enabled"}}


def test_unknown_provider_does_not_invent_reasoning_fields():
    assert build_openai_compatible_reasoning_kwargs(spec=SimpleNamespace(name="custom"), binding=None, model="plain", reasoning_effort=None) == {}

