import { describe, expect, it } from "vitest";
import {
  normalizeToolActivity,
  reduceToolActivityEvent,
  type ToolActivityMap,
} from "@/lib/tools/tool-activity-reducer";
import { projectToolActivity, projectToolTrace, toolErrorCopy, toolActivityLine } from "@/lib/chat/activity-projection";
import { activityFromToolBlock, toolBlockSummaryLine } from "@/lib/tools/tool-block-normalizer";
import { createInitialChatRuntimeState, reduceChatEvents } from "@/lib/event-reducer";
import type { ChatBlockDTO, ChatEventEnvelope } from "@/types/chat";
import type { ToolActivityDTO } from "@/types/tool";
import { RUN_ID, THREAD_ID } from "@/fixtures/chat/scenarios";

const base = { run_id: RUN_ID, thread_id: THREAD_ID, payload_version: 1 } as const;

function activity(overrides: Partial<ToolActivityDTO> = {}): ToolActivityDTO {
  return {
    tool_call_id: "call_p4_01",
    name: "query_member_profile",
    version: "v1",
    display_name: "读取健康档案",
    target: "server",
    status: "requested",
    round_index: 0,
    call_index: 0,
    revision: 1,
    display_args: { sections: ["过敏史", "慢性病"] },
    result_preview: null,
    source_refs: [],
    error: null,
    duplicate_of: null,
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

function toolEvent(type: string, sequence: number, payload: Record<string, unknown>): ChatEventEnvelope {
  return { ...base, type, event_id: `00000000-0000-0000-0000-0000000000${20 + sequence}`, sequence, timestamp: "2026-08-25T02:00:09Z", payload };
}

describe("tool activity reducer", () => {
  it("stores the full requested projection", () => {
    const event = toolEvent("tool.call.requested", 1, { tool_call_id: "call_p4_01", tool_name: "query_member_profile", round_index: 0, activity: activity() });
    const map = reduceToolActivityEvent({}, event);
    expect(map["call_p4_01"]?.status).toBe("requested");
    expect(map["call_p4_01"]?.display_args).toEqual({ sections: ["过敏史", "慢性病"] });
  });

  it("merges the partial started patch into an existing call", () => {
    let map: ToolActivityMap = reduceToolActivityEvent({}, toolEvent("tool.call.requested", 1, { activity: activity() }));
    map = reduceToolActivityEvent(map, toolEvent("tool.call.started", 2, { tool_call_id: "call_p4_01", status: "running", revision: 2, started_at: "2026-08-25T02:00:10Z" }));
    expect(map["call_p4_01"]?.status).toBe("running");
    expect(map["call_p4_01"]?.started_at).toBe("2026-08-25T02:00:10Z");
  });

  it("ignores a started patch without a prior requested projection", () => {
    const map = reduceToolActivityEvent({}, toolEvent("tool.call.started", 1, { tool_call_id: "ghost", status: "running", revision: 2 }));
    expect(map).toEqual({});
  });

  it("never regresses revisions on stale replay", () => {
    let map: ToolActivityMap = reduceToolActivityEvent({}, toolEvent("tool.result", 3, { activity: activity({ status: "completed", revision: 3, result_preview: "已读取 2 个健康档案分区" }) }));
    const before = map["call_p4_01"];
    map = reduceToolActivityEvent(map, toolEvent("tool.call.started", 2, { tool_call_id: "call_p4_01", status: "running", revision: 2 }));
    expect(map["call_p4_01"]).toBe(before);
    map = reduceToolActivityEvent(map, toolEvent("tool.call.requested", 1, { activity: activity() }));
    expect(map["call_p4_01"]).toBe(before);
  });

  it("degrades malformed payloads to null without throwing", () => {
    expect(normalizeToolActivity(null)).toBeNull();
    expect(normalizeToolActivity({ tool_call_id: "" })).toBeNull();
    expect(normalizeToolActivity({ tool_call_id: "x", status: "weird_status", name: 42 })).toMatchObject({ tool_call_id: "x", status: "requested", name: "unknown_tool" });
  });
});

describe("activity projection view model", () => {
  it("maps known tools to labels and summaries", () => {
    const view = projectToolActivity(activity({ status: "completed", revision: 3, result_preview: "已读取 2 个健康档案分区", source_refs: [{ source_id: "member_profile:42", type: "member_profile" }] }));
    expect(view.displayName).toBe("读取健康档案");
    expect(view.tone).toBe("success");
    expect(view.argSummary).toBe("读取：过敏史、慢性病");
    expect(view.resultLine).toBe("已读取 2 个健康档案分区");
    expect(view.sourceCount).toBe(1);
    expect(toolActivityLine(view)).toBe("读取健康档案 · 已读取 2 个健康档案分区");
  });

  it("maps error message keys to safe copy and degrades unknown codes", () => {
    expect(toolErrorCopy({ code: "timeout", message_key: "tool_timeout", retryable: true })).toEqual({ text: "工具执行超时", retryable: true });
    expect(toolErrorCopy({ code: "secret_code", message_key: "never_seen_before", retryable: false })).toEqual({ text: "工具执行出现问题", retryable: true });
    const view = projectToolActivity(activity({ status: "failed", revision: 3, error: { code: "tool_unavailable", message_key: "tool_unavailable", retryable: false } }));
    expect(view.errorLine).toBe("该工具当前不可用");
    expect(view.tone).toBe("error");
  });

  it("degrades unknown tool names to generic copy", () => {
    const view = projectToolActivity(activity({ name: "future_super_tool", display_name: "超能力", display_args: { secret: "raw" } }));
    expect(view.displayName).toBe("服务工具");
    expect(view.argSummary).toBeNull();
  });
});

describe("tool trace view model (CHAT-WEB-027 W3 verb/chip/detail)", () => {
  it("separates the action verb from the artifact chip instead of one joined string", () => {
    const view = projectToolTrace(activity({ status: "running", display_args: { sections: ["过敏史", "慢性病"] } }));
    expect(view.verb).toBe("查询会员档案");
    expect(view.chip).toBe("过敏史、慢性病");
  });

  it("only surfaces a detail line once terminal, combining result + source count", () => {
    const running = projectToolTrace(activity({ status: "running" }));
    expect(running.detail).toBeNull();
    const done = projectToolTrace(activity({
      status: "completed",
      revision: 3,
      result_preview: "已读取 2 个健康档案分区",
      source_refs: [{ source_id: "member_profile:42", type: "member_profile" }],
    }));
    expect(done.detail).toBe("已读取 2 个健康档案分区 · 引用 1 条资料");
  });

  it("falls back to displayName for unknown tools and null chip when no allow-listed arg matches", () => {
    const view = projectToolTrace(activity({ name: "future_super_tool", display_name: "超能力", display_args: { secret: "raw" } }));
    expect(view.verb).toBe("服务工具");
    expect(view.chip).toBeNull();
  });

  it("surfaces the error line as detail on failure, without a false source-count suffix", () => {
    const view = projectToolTrace(activity({ status: "failed", revision: 3, error: { code: "tool_unavailable", message_key: "tool_unavailable", retryable: false } }));
    expect(view.detail).toBe("该工具当前不可用");
  });
});

describe("tool block normalizer", () => {
  const toolCallBlock: ChatBlockDTO = {
    id: "b1", kind: "toolCall", status: "streaming", revision: 2, order_key: 1800,
    tool_call_id: "call_p4_01", parent_tool_call_id: null, parent_block_id: null, node_role: "toolExecution",
    payload: { tool_call_id: "call_p4_01", name: "query_member_profile", display_name: "读取健康档案", status: "running", revision: 2, display_args: { sections: ["过敏史"] } },
  };

  it("builds an activity view from the persisted block payload", () => {
    const view = activityFromToolBlock(toolCallBlock);
    expect(view?.status).toBe("running");
    expect(view?.display_args).toEqual({ sections: ["过敏史"] });
    expect(toolBlockSummaryLine(toolCallBlock)).toContain("读取健康档案");
  });

  it("treats a failed toolCall block as cancelled and a ready toolResult as completed", () => {
    expect(activityFromToolBlock({ ...toolCallBlock, status: "failed" })?.status).toBe("cancelled");
    const resultBlock = { ...toolCallBlock, kind: "toolResult" as const, status: "ready" as const, payload: { tool_call_id: "call_p4_01", result_preview: "已读取 2 个健康档案分区" } };
    expect(activityFromToolBlock(resultBlock)?.status).toBe("completed");
  });

  it("returns null for non-tool blocks", () => {
    expect(activityFromToolBlock({ ...toolCallBlock, kind: "text" })).toBeNull();
  });
});

describe("event reducer integration", () => {
  it("routes tool events into toolCallsByRun and applies block updates", () => {
    const events: ChatEventEnvelope[] = [
      toolEvent("tool.call.requested", 1, { activity: activity() }),
      toolEvent("block.created", 2, {
        message_id: "1002",
        block: { id: "b1", kind: "toolCall", status: "streaming", revision: 1, order_key: 1800, node_role: "toolExecution", tool_call_id: "call_p4_01", payload: { tool_call_id: "call_p4_01", status: "requested", revision: 1, display_args: { sections: ["过敏史"] } } },
      }),
      toolEvent("tool.call.started", 3, { tool_call_id: "call_p4_01", status: "running", revision: 2, started_at: "2026-08-25T02:00:10Z" }),
      toolEvent("block.updated", 4, {
        message_id: "1002", block_id: "b1", kind: "toolCall", status: "streaming", revision: 2, order_key: 1800,
        block: { id: "b1", kind: "toolCall", status: "streaming", revision: 2, order_key: 1800, node_role: "toolExecution", tool_call_id: "call_p4_01", payload: { tool_call_id: "call_p4_01", status: "running", revision: 2 } },
      }),
      toolEvent("tool.result", 5, { activity: activity({ status: "completed", revision: 3, result_preview: "已读取 2 个健康档案分区" }) }),
    ];
    const state = reduceChatEvents(createInitialChatRuntimeState(), events);
    expect(state.toolCallsByRun[RUN_ID]["call_p4_01"].status).toBe("completed");
    expect(state.blocksById["b1"].payload.status).toBe("running");
    expect(state.blocksById["b1"].revision).toBe(2);
    // Tool events are known activities now: they must not leak into unknownActivities.
    expect(state.unknownActivitiesByRun[RUN_ID]).toBeUndefined();
  });
});
