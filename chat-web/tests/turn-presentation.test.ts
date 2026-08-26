import { describe, expect, it } from "vitest";
import {
  buildTurnPresentation,
  classifyTurnBlock,
  collectToolActivityRows,
  selectPresentationBlocks,
  turnVisibleText,
} from "@/lib/chat/turn-presentation";
import { projectTurnActivity } from "@/lib/chat/turn-activity-projector";
import type { ChatBlockDTO } from "@/types/chat";

function block(overrides: Partial<ChatBlockDTO> & { id: string; kind: string }): ChatBlockDTO {
  return {
    status: "ready",
    revision: 1,
    order_key: 1,
    node_role: "timeline",
    payload: {},
    ...overrides,
  };
}

describe("classifyTurnBlock", () => {
  it("separates thinking, activity, content and presentation kinds", () => {
    expect(classifyTurnBlock(block({ id: "t", kind: "deepThought" }))).toBe("thinking");
    expect(classifyTurnBlock(block({ id: "c", kind: "toolCall", tool_call_id: "k1" }))).toBe("activity");
    expect(classifyTurnBlock(block({ id: "r", kind: "toolResult", tool_call_id: "k1" }))).toBe("activity");
    expect(classifyTurnBlock(block({ id: "x", kind: "text" }))).toBe("content");
    expect(classifyTurnBlock(block({ id: "h", kind: "html" }))).toBe("content");
    expect(classifyTurnBlock(block({ id: "s", kind: "healthCards" }))).toBe("presentation");
  });
});

describe("buildTurnPresentation", () => {
  it("groups blocks by category preserving order", () => {
    const blocks = [
      block({ id: "think", kind: "deepThought", order_key: "1" }),
      block({ id: "call", kind: "toolCall", tool_call_id: "k1", order_key: "2" }),
      block({ id: "txt", kind: "text", order_key: "3", payload: { text: { _0: "回答" } } }),
      block({ id: "card", kind: "healthCards", order_key: "4", parent_tool_call_id: "k1" }),
      block({ id: "result", kind: "toolResult", tool_call_id: "k1", order_key: "5" }),
    ];
    const presentation = buildTurnPresentation(blocks, "m1", "assistant");
    expect(presentation.thinkingBlocks.map((b) => b.id)).toEqual(["think"]);
    expect(presentation.activityBlocks.map((b) => b.id)).toEqual(["call", "result"]);
    expect(presentation.contentBlocks.map((b) => b.id)).toEqual(["txt"]);
    expect(presentation.presentationBlocks.map((b) => b.id)).toEqual(["card"]);
    expect(presentation.hasText).toBe(true);
  });
});

describe("turnVisibleText", () => {
  it("only concatenates content blocks, excluding tool and presentation", () => {
    const blocks = [
      block({ id: "a", kind: "text", payload: { text: { _0: "第一段" } } }),
      block({ id: "b", kind: "toolCall", tool_call_id: "k1" }),
      block({ id: "c", kind: "html", payload: { html: { _0: { text: "第二段" } } } }),
      block({ id: "d", kind: "healthCards" }),
    ];
    expect(turnVisibleText(blocks)).toBe("第一段\n\n第二段");
  });
});

describe("selectPresentationBlocks", () => {
  it("drops the generic tool card when a domain card shares the call id", () => {
    const blocks = [
      block({ id: "advice", kind: "healthCards", parent_tool_call_id: "k1" }),
      block({ id: "generic", kind: "tool", parent_tool_call_id: "k1" }),
    ];
    expect(selectPresentationBlocks(blocks).map((b) => b.id)).toEqual(["advice"]);
  });

  it("keeps the generic tool card when no domain card exists for that call", () => {
    const blocks = [block({ id: "generic", kind: "tool", parent_tool_call_id: "k9" })];
    expect(selectPresentationBlocks(blocks).map((b) => b.id)).toEqual(["generic"]);
  });
});

describe("collectToolActivityRows", () => {
  it("collapses a call and its result into one row", () => {
    const blocks = [
      block({ id: "call", kind: "toolCall", tool_call_id: "k1", order_key: 1, payload: { tool_call_id: "k1", status: "requested" } }),
      block({ id: "result", kind: "toolResult", tool_call_id: "k1", order_key: 2, payload: { tool_call_id: "k1", result_preview: "已读取" } }),
    ];
    const rows = collectToolActivityRows(blocks);
    expect(rows).toHaveLength(1);
    expect(rows[0].tool_call_id).toBe("k1");
  });

  it("prefers the live projection when its revision is higher", () => {
    const blocks = [block({ id: "call", kind: "toolCall", tool_call_id: "k1", order_key: 1, payload: { tool_call_id: "k1", status: "requested" } })];
    const live = {
      tool_call_id: "k1", name: "x", version: "v1", display_name: "工具", target: "server" as const,
      status: "completed" as const, round_index: 0, call_index: 0, revision: 9,
      display_args: {}, result_preview: null, source_refs: [], error: null, duplicate_of: null, started_at: null, finished_at: null,
    };
    const rows = collectToolActivityRows(blocks, () => live);
    expect(rows[0].status).toBe("completed");
    expect(rows[0].revision).toBe(9);
  });
});

describe("projectTurnActivity", () => {
  it("reports using_tools while any tool row is still running", () => {
    const running = { tool_call_id: "k1", name: "x", version: "v1", display_name: "工具", target: "server" as const, status: "running" as const, round_index: 0, call_index: 0, revision: 1, display_args: {}, result_preview: null, source_refs: [], error: null, duplicate_of: null, started_at: null, finished_at: null };
    const vm = projectTurnActivity({ runId: "r1", runStatus: "running", assistantStatus: "using_tools", toolRows: [running], contentStreaming: false });
    expect(vm.phase).toBe("using_tools");
    expect(vm.anyToolRunning).toBe(true);
    expect(vm.isRunning).toBe(true);
    expect(vm.isTerminal).toBe(false);
    expect(vm.publicStatusLabel).toBe("正在使用工具");
  });

  it("maps terminal run status to a collapsed completed phase", () => {
    const vm = projectTurnActivity({ runId: "r1", runStatus: "completed", assistantStatus: null, toolRows: [], contentStreaming: false });
    expect(vm.phase).toBe("completed");
    expect(vm.isRunning).toBe(false);
    expect(vm.isTerminal).toBe(true);
    expect(vm.publicStatusLabel).toBe("已完成");
  });

  it("degrades unknown assistant status to a generic label", () => {
    const vm = projectTurnActivity({ runId: "r1", runStatus: "running", assistantStatus: "future_status", toolRows: [], contentStreaming: true });
    expect(vm.publicStatusLabel).toBe("正在组织回答");
  });
});