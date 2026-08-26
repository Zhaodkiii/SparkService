from __future__ import annotations

from chat_sync.ai_runtime.capabilities.protocol import CapabilityManifest


manifest = CapabilityManifest(
    id="chat",
    version="v1",
    title="普通对话",
    description="围绕当前 Thread 进行安全的文本对话，可使用已授权的只读工具。",
    execution_mode="loop",
    prompt_version="chat.prompt.v1",
    input_schema={
        "type": "object",
        "properties": {"content": {"type": "string", "maxLength": 12000}},
        "additionalProperties": False,
    },
    required_context=("thread",),
    result_kinds=("text", "tool", "searchSummary"),
    max_rounds=8,
    max_context_tokens=8192,
)
manifest.validate()

