from __future__ import annotations

from chat_sync.ai_runtime.protocols.tool_protocol import BaseTool, ToolDefinition, ToolResult
from chat_sync.ai_runtime.tools.ask_user_schema import build_ask_user_payload


class AskUserTool(BaseTool):
    """Turns a model clarification request into a durable P5 pause."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="ask_user",
            description="向用户提出结构化澄清问题，等待回答后继续当前对话。",
            raw_parameters={
                "type": "object",
                "properties": {
                    "intro": {"type": "string"},
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "questions": {"type": "array", "items": {"type": "object"}},
                },
                "additionalProperties": False,
            },
        )

    async def execute(self, *, _execution_context=None, **arguments) -> ToolResult:
        payload, error = build_ask_user_payload(
            questions=arguments.get("questions"),
            intro=arguments.get("intro"),
            question=arguments.get("question"),
            options=arguments.get("options"),
        )
        if payload is None:
            return ToolResult(
                content=error or "问题格式无效。",
                success=False,
                metadata={"error_code": "ask_user_invalid_request"},
            )
        return ToolResult(
            content="等待用户回答后继续。",
            pause_for_user={
                "kind": "ask_user",
                "request_schema": payload.to_dict(),
                "expires_in_seconds": 24 * 60 * 60,
                "tool_version": "v1",
                "fallback_behavior": "return_unavailable",
            },
            metadata={"tool": "ask_user"},
        )


__all__ = ["AskUserTool"]
