"""Server-side schemas for tools executed by a trusted client device."""

from .._client_tools import (
    FetchEnergyDetailsTool,
    FetchNutritionDetailsTool,
    FetchSleepDetailsTool,
    FetchStepDetailsTool,
    FetchWorkoutDetailsTool,
    GetCurrentLocationTool,
)

__all__ = [
    "FetchStepDetailsTool", "FetchEnergyDetailsTool", "FetchNutritionDetailsTool",
    "FetchSleepDetailsTool", "FetchWorkoutDetailsTool", "GetCurrentLocationTool",
]
