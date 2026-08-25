from chat_sync.ai_runtime.providers.request_compat import error_text, is_image_input_unsupported, is_stream_options_unsupported, is_tool_schema_unsupported


def test_error_text_uses_response_body_and_classifiers():
    error = type("E", (), {"response": type("R", (), {"text": "unknown parameter stream_options"})()})()
    assert "stream_options" in error_text(error)
    assert is_stream_options_unsupported(error)
    assert is_tool_schema_unsupported(Exception("function_declarations not supported"))
    assert is_image_input_unsupported(Exception("vision image_url rejected"))

