from __future__ import annotations

from typing import Any

from chat_sync.ai_runtime.protocols.tool_protocol import BaseTool, ToolDefinition, ToolResult


class _ClientTool(BaseTool):
    tool_name = ""
    description = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(name=self.tool_name, description=self.description, raw_parameters=self.parameters)

    async def execute(self, *, _execution_context=None, **arguments) -> ToolResult:
        request_schema = {"tool": self.tool_name, "tool_version": "v1", "arguments": arguments, "limits": {"max_days": 31, "max_items": 100}}
        return ToolResult(
            content=f"等待客户端执行 {self.tool_name}。",
            pause_for_user={
                "kind": "client_tool", "request_schema": request_schema,
                "required_platform": "ios", "required_capability": self.tool_name,
                "tool_version": "v1", "expires_in_seconds": 600,
                "fallback_behavior": "return_unavailable",
            },
            metadata={"target": "client", "tool": self.tool_name},
        )


class FetchStepDetailsTool(_ClientTool):
    tool_name = "fetch_step_details"
    description = "从 iOS HealthKit 读取指定日期范围的每日步数聚合。"
    parameters = {"type": "object", "properties": {"start_at": {"type": "string"}, "end_at": {"type": "string"}}, "required": ["start_at", "end_at"], "additionalProperties": False}


class FetchEnergyDetailsTool(_ClientTool):
    tool_name = "fetch_energy_details"
    description = "从 iOS HealthKit 读取活动和静息能量聚合。"
    parameters = {"type": "object", "properties": {"start_at": {"type": "string"}, "end_at": {"type": "string"}}, "required": ["start_at", "end_at"], "additionalProperties": False}


class FetchNutritionDetailsTool(_ClientTool):
    tool_name = "fetch_nutrition_details"
    description = "从 iOS HealthKit 读取营养摄入聚合。"
    parameters = {"type": "object", "properties": {"start_at": {"type": "string"}, "end_at": {"type": "string"}}, "required": ["start_at", "end_at"], "additionalProperties": False}


class FetchSleepDetailsTool(_ClientTool):
    tool_name = "fetch_sleep_details"
    description = "从 iOS HealthKit 读取每日睡眠摘要。"
    parameters = {"type": "object", "properties": {"start_at": {"type": "string"}, "end_at": {"type": "string"}}, "required": ["start_at", "end_at"], "additionalProperties": False}


class FetchWorkoutDetailsTool(_ClientTool):
    tool_name = "fetch_workout_details"
    description = "从 iOS HealthKit 读取运动摘要。"
    parameters = {"type": "object", "properties": {"start_at": {"type": "string"}, "end_at": {"type": "string"}}, "required": ["start_at", "end_at"], "additionalProperties": False}


class GetCurrentLocationTool(_ClientTool):
    tool_name = "get_current_location"
    description = "请求 iOS 获取一次当前定位，不进行后台连续跟踪。"
    parameters = {"type": "object", "properties": {"max_age_seconds": {"type": "integer"}, "purpose": {"type": "string"}}, "required": [], "additionalProperties": False}


__all__ = ["FetchStepDetailsTool", "FetchEnergyDetailsTool", "FetchNutritionDetailsTool", "FetchSleepDetailsTool", "FetchWorkoutDetailsTool", "GetCurrentLocationTool"]
