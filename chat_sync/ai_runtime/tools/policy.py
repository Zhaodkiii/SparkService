from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID


TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    name: str
    version: str = "v1"
    target: Literal["server", "client"] = "server"
    supported_platforms: tuple[str, ...] = ()
    risk: Literal["read_only"] = "read_only"
    side_effect: Literal["none"] = "none"
    required_permissions: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    concurrency_safe: bool = True
    timeout_seconds: float = 10.0
    max_result_tokens: int = 2000
    max_attempts: int = 1

    def validate(self) -> None:
        if not TOOL_NAME_RE.fullmatch(self.name):
            raise ValueError(f"invalid tool name: {self.name}")
        if self.target not in {"server", "client"} or self.risk != "read_only" or self.side_effect != "none":
            raise ValueError(f"only read-only tools are permitted: {self.name}")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 120:
            raise ValueError(f"invalid tool timeout: {self.name}")
        if self.max_result_tokens < 1 or self.max_result_tokens > 10000:
            raise ValueError(f"invalid tool result limit: {self.name}")
        if self.max_attempts < 1 or self.max_attempts > 2:
            raise ValueError(f"invalid tool attempt limit: {self.name}")


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    run_id: UUID
    thread_id: UUID
    user_id: int
    member_id: int | None = None
    context_snapshot_id: int | None = None
    context_hash: str = ""
    lease_token: UUID | None = None
    request_id: str = ""
    deadline_at: datetime | None = None


def canonical_tool_args(name: str, version: str, arguments: dict[str, Any]) -> str:
    import hashlib
    import json

    payload = json.dumps(
        {"name": name, "version": version, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_schema(schema: dict[str, Any], value: Any, *, path: str = "arguments") -> list[str]:
    """Small dependency-free JSON-schema subset used at the execution gate."""
    errors: list[str] = []
    if not isinstance(schema, dict):
        return [f"{path}: schema_invalid"]
    expected = schema.get("type")
    type_ok = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    if expected in type_ok and not type_ok[expected]:
        return [f"{path}: expected_{expected}"]
    if "enum" in schema and value not in schema.get("enum", []):
        errors.append(f"{path}: enum")
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: required")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key}: additional_property")
        for key, child in value.items():
            if key in properties:
                errors.extend(validate_schema(properties[key], child, path=f"{path}.{key}"))
    elif isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, child in enumerate(value):
                errors.extend(validate_schema(items, child, path=f"{path}[{index}]"))
    if isinstance(value, str):
        if len(value) > int(schema.get("maxLength", 32768)):
            errors.append(f"{path}: max_length")
    if isinstance(value, list) and len(value) > int(schema.get("maxItems", 100)):
        errors.append(f"{path}: max_items")
    if isinstance(value, dict) and len(value) > int(schema.get("maxProperties", 64)):
        errors.append(f"{path}: max_properties")
    return errors


__all__ = ["ToolExecutionContext", "ToolPolicy", "canonical_tool_args", "validate_schema"]
