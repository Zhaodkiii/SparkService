from chat_sync.ai_runtime.protocols.tool_protocol import ToolDefinition, ToolParameter, ToolResult


def test_array_schema_has_items_and_required_is_stable():
    definition = ToolDefinition(
        name="health_summary",
        description="Read a summary",
        parameters=[ToolParameter("metrics", "array"), ToolParameter("days", "integer", required=False)],
    )
    schema = definition.to_openai_schema()
    assert schema["function"]["parameters"]["required"] == ["metrics"]
    assert schema["function"]["parameters"]["properties"]["metrics"]["items"] == {"type": "string"}


def test_raw_parameters_take_precedence_and_result_is_stringifiable():
    definition = ToolDefinition("x", "x", raw_parameters={"type": "object", "properties": {"q": {"type": "string"}}})
    assert definition.to_openai_schema()["function"]["parameters"]["properties"]["q"]["type"] == "string"
    result = ToolResult(content="ok", success=False, pause_for_user={"kind": "ask_user"})
    assert str(result) == "ok"
    assert result.pause_for_user["kind"] == "ask_user"

