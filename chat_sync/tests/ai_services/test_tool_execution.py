from __future__ import annotations

import asyncio
import uuid

from django.test import SimpleTestCase

from chat_sync.ai_runtime.protocols.tool_protocol import BaseTool, ToolDefinition, ToolResult
from chat_sync.ai_runtime.tools.dispatcher import dispatch_tool_calls
from chat_sync.ai_runtime.tools.executor import execute_tool_call
from chat_sync.ai_runtime.tools.policy import ToolExecutionContext, ToolPolicy
from chat_sync.ai_runtime.tools.registry import ToolRegistry
from chat_sync.ai_runtime.tools.scoped_registry import ScopedToolRegistry


class _FlakyTool(BaseTool):
    def __init__(self, fail_times: int = 1) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(name="flaky_tool", description="flaky", parameters=[])

    async def execute(self, **kwargs) -> ToolResult:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("transient failure")
        return ToolResult(content="ok", success=True)


def _scoped(fail_times: int, max_attempts: int) -> tuple[ScopedToolRegistry, _FlakyTool]:
    tool = _FlakyTool(fail_times=fail_times)
    registry = ToolRegistry()
    registry.register(tool, ToolPolicy("flaky_tool", max_attempts=max_attempts))
    return ScopedToolRegistry(registry, ["flaky_tool"]), tool


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(run_id=uuid.uuid4(), thread_id=uuid.uuid4(), user_id=1)


class ToolExecutorRetryTests(SimpleTestCase):
    def test_retries_retryable_failure_within_policy_budget(self):
        scoped, tool = _scoped(fail_times=1, max_attempts=2)
        progress: list[tuple[str, float | None]] = []

        async def run():
            async def on_progress(msg, pct):
                progress.append((msg, pct))

            return await execute_tool_call(scoped, name="flaky_tool", arguments={}, context=_context(), on_progress=on_progress)

        result = asyncio.run(run())
        self.assertTrue(result.success)
        self.assertEqual(tool.calls, 2)
        self.assertEqual(result.metadata.get("attempts"), 2)
        self.assertEqual(progress, [("第 1 次执行失败，正在重试…", None)])

    def test_no_retry_when_policy_budget_is_one(self):
        scoped, tool = _scoped(fail_times=1, max_attempts=1)
        progress: list[tuple[str, float | None]] = []

        async def run():
            async def on_progress(msg, pct):
                progress.append((msg, pct))

            return await execute_tool_call(scoped, name="flaky_tool", arguments={}, context=_context(), on_progress=on_progress)

        result = asyncio.run(run())
        self.assertFalse(result.success)
        self.assertEqual(result.metadata["error_code"], "tool_execution_failed")
        self.assertTrue(result.metadata["retryable"])
        self.assertEqual(tool.calls, 1)
        self.assertEqual(progress, [])


class ToolDispatcherProgressTests(SimpleTestCase):
    def test_dispatcher_scopes_progress_by_call_id(self):
        tool = _FlakyTool(fail_times=1)
        registry = ToolRegistry()
        registry.register(tool, ToolPolicy("flaky_tool", max_attempts=2))
        scoped = ScopedToolRegistry(registry, ["flaky_tool"])
        progress: list[tuple[str, str, float | None]] = []

        async def run():
            async def on_progress(call_id, msg, pct):
                progress.append((call_id, msg, pct))

            return await dispatch_tool_calls(
                [{"id": "call_1", "name": "flaky_tool", "arguments": {}}],
                registry=scoped,
                context=_context(),
                on_progress=on_progress,
            )

        items = asyncio.run(run())
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].result.success)
        self.assertEqual(progress, [("call_1", "第 1 次执行失败，正在重试…", None)])


class ToolCrossRoundDedupTests(SimpleTestCase):
    def _dispatch(self, scoped, seen, calls):
        async def run():
            return await dispatch_tool_calls(calls, registry=scoped, context=_context(), seen=seen)

        return asyncio.run(run())

    def test_identical_success_call_dedups_across_rounds(self):
        tool = _FlakyTool(fail_times=0)
        registry = ToolRegistry()
        registry.register(tool, ToolPolicy("flaky_tool", max_attempts=1))
        scoped = ScopedToolRegistry(registry, ["flaky_tool"])
        seen: dict[str, str] = {}

        first = self._dispatch(scoped, seen, [{"id": "call_0", "name": "flaky_tool", "arguments": {"q": "x"}}])
        second = self._dispatch(scoped, seen, [{"id": "call_1", "name": "flaky_tool", "arguments": {"q": "x"}}])

        self.assertTrue(first[0].result.success)
        self.assertEqual(second[0].duplicate_of, "call_0")
        self.assertEqual(second[0].result.metadata["error_code"], "duplicate_tool_call")
        self.assertEqual(tool.calls, 1)

    def test_empty_argument_retry_dedups_across_rounds(self):
        tool = _FlakyTool(fail_times=0)
        registry = ToolRegistry()
        registry.register(tool, ToolPolicy("flaky_tool", max_attempts=1))
        scoped = ScopedToolRegistry(registry, ["flaky_tool"])
        seen: dict[str, str] = {}

        first = self._dispatch(scoped, seen, [{"id": "r0", "name": "flaky_tool", "arguments": {}}])
        second = self._dispatch(scoped, seen, [{"id": "r1", "name": "flaky_tool", "arguments": {}}])

        self.assertEqual(tool.calls, 1)
        self.assertEqual(second[0].duplicate_of, "r0")

    def test_failed_call_is_not_deduped_so_retry_runs(self):
        tool = _FlakyTool(fail_times=100)
        registry = ToolRegistry()
        registry.register(tool, ToolPolicy("flaky_tool", max_attempts=1))
        scoped = ScopedToolRegistry(registry, ["flaky_tool"])
        seen: dict[str, str] = {}

        first = self._dispatch(scoped, seen, [{"id": "r0", "name": "flaky_tool", "arguments": {}}])
        second = self._dispatch(scoped, seen, [{"id": "r1", "name": "flaky_tool", "arguments": {}}])

        self.assertFalse(first[0].result.success)
        self.assertFalse(second[0].result.success)
        self.assertEqual(second[0].duplicate_of, "")
        self.assertEqual(tool.calls, 2)