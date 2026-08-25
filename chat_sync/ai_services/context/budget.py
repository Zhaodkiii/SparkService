from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudget:
    window: int
    reserved_output: int
    safety_margin: int
    input_budget: int
    history_budget: int


def resolve_budget(*, window: int, reserved_output: int, history_ratio: float = 0.35) -> ContextBudget:
    window = max(1024, int(window))
    reserved_output = max(0, min(int(reserved_output), window - 256))
    margin = max(512, int(window * 0.05))
    input_budget = max(256, window - reserved_output - margin)
    return ContextBudget(window, reserved_output, margin, input_budget, max(128, int(input_budget * history_ratio)))
