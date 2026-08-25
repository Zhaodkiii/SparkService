"""Versioned, framework-free contracts for Spark chat capabilities."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


class CapabilityUnavailable(ValueError):
    def __init__(self, capability_id: str, reason: str = "unavailable") -> None:
        self.capability_id = capability_id
        self.reason = reason
        super().__init__(f"capability {capability_id!r} is {reason}")


@dataclass(frozen=True, slots=True)
class CapabilityStage:
    id: str
    title: str
    order: int
    kind: Literal["model", "tool", "artifact", "approval"] = "model"
    timeout_seconds: int = 120
    max_attempts: int = 1

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", self.id):
            raise ValueError(f"invalid capability stage id: {self.id}")
        if self.order < 0 or self.timeout_seconds < 1 or not 1 <= self.max_attempts <= 3:
            raise ValueError(f"invalid capability stage policy: {self.id}")


@dataclass(frozen=True, slots=True)
class CapabilityManifest:
    id: str
    version: str
    title: str
    description: str
    execution_mode: Literal["loop", "staged", "reader_link"] = "loop"
    prompt_version: str = "chat.prompt.v1"
    input_schema: dict[str, Any] = field(default_factory=dict)
    required_context: tuple[str, ...] = ()
    owned_tools: tuple[str, ...] = ()
    result_kinds: tuple[str, ...] = ("text",)
    stages: tuple[CapabilityStage, ...] = ()
    max_rounds: int = 8
    max_context_tokens: int = 8192
    enabled: bool = True
    availability_reason: str = ""

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", self.id):
            raise ValueError(f"invalid capability id: {self.id}")
        if not re.fullmatch(r"v[0-9]+(?:\.[0-9]+)?", self.version):
            raise ValueError(f"invalid capability version: {self.version}")
        if self.execution_mode not in {"loop", "staged", "reader_link"}:
            raise ValueError(f"invalid execution mode: {self.execution_mode}")
        if not 1 <= self.max_rounds <= 32 or self.max_context_tokens < 256:
            raise ValueError(f"invalid capability limits: {self.id}")
        if len(self.owned_tools) > 32 or len(self.result_kinds) > 32:
            raise ValueError(f"capability contract too large: {self.id}")
        for stage in self.stages:
            stage.validate()
        if tuple(sorted(self.stages, key=lambda item: item.order)) != self.stages:
            raise ValueError(f"capability stages must be ordered: {self.id}")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["required_context"] = list(self.required_context)
        value["owned_tools"] = list(self.owned_tools)
        value["result_kinds"] = list(self.result_kinds)
        value["stages"] = [asdict(stage) for stage in self.stages]
        value["manifest_hash"] = self.manifest_hash
        return value

    @property
    def key(self) -> str:
        return f"{self.id}@{self.version}"

    @property
    def manifest_hash(self) -> str:
        value = asdict(self)
        value.pop("availability_reason", None)
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

