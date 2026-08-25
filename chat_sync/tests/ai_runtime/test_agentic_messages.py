from chat_sync.ai_runtime.agentic.messages import assistant_message_with_tool_calls


def test_tool_call_message_is_provider_neutral_and_deterministic():
    message = assistant_message_with_tool_calls("", [{"id": "call-1", "name": "read_health", "arguments": ""}])
    assert message == {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "read_health", "arguments": "{}"}}],
    }

