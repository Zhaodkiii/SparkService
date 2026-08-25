"""Provider-neutral tool definitions and results.

Migrated from DeepTutor's ``core/tool_protocol.py`` and intentionally kept
framework-free. Spark authorization, persistence, and execution are added in
later phases.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass
class ToolParameter:
    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[str] | None = None
    items: dict[str, Any] | None = None

    def to_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": self.type, "description": self.description}
        if self.enum:
            schema["enum"] = self.enum
        if self.type == "array":
            schema["items"] = self.items if self.items is not None else {"type": "string"}
        return schema


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    raw_parameters: dict[str, Any] | None = None

    def to_openai_schema(self) -> dict[str, Any]:
        if self.raw_parameters is not None:
            schema = dict(self.raw_parameters)
            schema.setdefault("type", "object")
            schema.setdefault("properties", {})
        else:
            properties = {p.name: p.to_schema() for p in self.parameters}
            schema = {
                "type": "object",
                "properties": properties,
                "required": [p.name for p in self.parameters if p.required],
            }
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": schema},
        }


@dataclass
class ToolAlias:
    name: str
    description: str = ""
    input_format: str = ""
    when_to_use: str = ""
    phase: str = ""


@dataclass
class ToolPromptHints:
    short_description: str = ""
    when_to_use: str = ""
    input_format: str = ""
    guideline: str = ""
    note: str = ""
    phase: str = ""
    aliases: list[ToolAlias] = field(default_factory=list)


@dataclass
class ToolResult:
    content: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    terminate_turn: bool = False
    pause_for_user: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.content


@dataclass(frozen=True)
class ToolPauseRequest:
    """Durable pause instruction returned by a tool executor."""

    kind: Literal["ask_user", "client_tool"]
    request_schema: dict[str, Any]
    expires_in_seconds: int = 600
    required_platform: str = ""
    required_capability: str = ""
    tool_version: str = "v1"
    fallback_behavior: str = "return_unavailable"


@dataclass(frozen=True)
class AgentLoopOutcome:
    kind: Literal["completed", "paused"]
    final_text: str = ""
    pause: ToolPauseRequest | None = None
    pause_tool_call_id: str = ""


class ToolEventSink(Protocol):
    async def __call__(
        self,
        event_type: str,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None: ...


class ToolLookup(Protocol):
    def get(self, name: str) -> "BaseTool | None": ...
    def get_enabled(self, names: list[str]) -> list["BaseTool"]: ...
    def get_definitions(self, names: list[str] | None = None) -> list[ToolDefinition]: ...
    async def execute(self, name: str, /, **kwargs: Any) -> Any: ...


class BaseTool(ABC):
    deferred: bool = False

    @abstractmethod
    def get_definition(self) -> ToolDefinition:
        raise NotImplementedError

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError

    def get_prompt_hints(self, language: str = "en") -> ToolPromptHints:
        return ToolPromptHints(short_description=self.get_definition().description)

    @property
    def name(self) -> str:
        return self.get_definition().name


def provider_identity(tool: Any) -> tuple[str, str]:
    kind = str(getattr(tool, "provider_kind", "") or "")
    provider_id = str(getattr(tool, "provider_id", "") or getattr(tool, "server_name", "") or "")
    return kind, provider_id


__all__ = [
    "BaseTool", "ToolAlias", "ToolDefinition", "ToolEventSink", "ToolLookup",
    "ToolParameter", "ToolPromptHints", "ToolResult", "ToolPauseRequest", "AgentLoopOutcome", "provider_identity",
]
