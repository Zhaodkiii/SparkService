import { describe, expect, it } from "vitest";
import { buildTurnTrace, isAgentRoundEvent, reduceAgentRoundEvent } from "@/lib/chat/turn-trace-reducer";
import type { ChatEventEnvelope } from "@/types/chat";
import type { ToolActivityDTO } from "@/types/tool";

function event(type: string, payload: Record<string, unknown>, sequence = 1): ChatEventEnvelope {
  return {
    type,
    event_id: `e-${sequence}-${type.replaceAll(".", "-")}`,
    payload_version: 1,
    run_id: "r1",
    thread_id: "t1",
    sequence,
    timestamp: "2026-08-25T00:00:00Z",
    payload,
  };
}

function tool(overrides: Partial<ToolActivityDTO> & { tool_call_id: string }): ToolActivityDTO {
  return {
    name: "read_source", version: "v1", display_name: "读取资料", target: "server",
    status: "completed", round_index: 0, call_index: 0, revision: 1,
    display_args: {}, result_preview: null, source_refs: [], error: null, duplicate_of: null,
    started_at: null, finished_at: null, progress_message: null, progress_percent: null,
    ...overrides,
  };
}

describe("isAgentRoundEvent", () => {
  it("recognises the four public round event types only", () => {
    expect(isAgentRoundEvent("agent.round.started")).toBe(true);
    expect(isAgentRoundEvent("agent.round.delta")).toBe(true);
    expect(isAgentRoundEvent("agent.round.completed")).toBe(true);
    expect(isAgentRoundEvent("agent.round.failed")).toBe(true);
    expect(isAgentRoundEvent("block.delta")).toBe(false);
  });
});

describe("reduceAgentRoundEvent", () => {
  it("accumulates public summary and narration content, then completes", () => {
    let rounds = reduceAgentRoundEvent({}, event("agent.round.started", { round_id: "r0", index: 0, call_id: "c0" }));
    rounds = reduceAgentRoundEvent(rounds, event("agent.round.delta", { round_id: "r0", channel: "public_reasoning_summary", text_delta: "先查" }, 2));
    rounds = reduceAgentRoundEvent(rounds, event("agent.round.delta", { round_id: "r0", channel: "assistant_content", text_delta: "我先看看" }, 3));
    rounds = reduceAgentRoundEvent(rounds, event("agent.round.completed", { round_id: "r0", call_role: "narration", finish_reason: "tool_calls" }, 4));

    const round = rounds["r0"];
    expect(round.status).toBe("completed");
    expect(round.call_role).toBe("narration");
    expect(round.public_summary).toBe("先查");
    expect(round.content).toBe("我先看看");
    expect(round.finish_reason).toBe("tool_calls");
  });

  it("marks a failed round with a stable error code", () => {
    let rounds = reduceAgentRoundEvent({}, event("agent.round.started", { round_id: "r0", index: 0, call_id: "c0" }));
    rounds = reduceAgentRoundEvent(rounds, event("agent.round.failed", { round_id: "r0", error_code: "provider_timeout", retryable: true }, 2));
    expect(rounds["r0"].status).toBe("failed");
    expect(rounds["r0"].error_code).toBe("provider_timeout");
    expect(rounds["r0"].retryable).toBe(true);
  });

  it("ignores unknown delta channels without throwing", () => {
    let rounds = reduceAgentRoundEvent({}, event("agent.round.started", { round_id: "r0", index: 0, call_id: "c0" }));
    rounds = reduceAgentRoundEvent(rounds, event("agent.round.delta", { round_id: "r0", channel: "raw_chain_of_thought", text_delta: "secret" }, 2));
    expect(rounds["r0"].public_summary).toBe("");
    expect(rounds["r0"].content).toBe("");
  });

  it("ignores a duplicate agent.round.started for an already-known round", () => {
    let rounds = reduceAgentRoundEvent({}, event("agent.round.started", { round_id: "r0", index: 0, call_id: "c0" }));
    rounds = reduceAgentRoundEvent(rounds, event("agent.round.delta", { round_id: "r0", channel: "assistant_content", text_delta: "已完成" }, 2));
    const before = rounds["r0"];
    rounds = reduceAgentRoundEvent(rounds, event("agent.round.started", { round_id: "r0", index: 0, call_id: "c0" }, 3));
    expect(rounds["r0"]).toBe(before);
  });

  it("never mutates a terminal round's public content on a late/replayed delta (no rollback rule)", () => {
    let rounds = reduceAgentRoundEvent({}, event("agent.round.started", { round_id: "r0", index: 0, call_id: "c0" }));
    rounds = reduceAgentRoundEvent(rounds, event("agent.round.delta", { round_id: "r0", channel: "assistant_content", text_delta: "已完成回答" }, 2));
    rounds = reduceAgentRoundEvent(rounds, event("agent.round.completed", { round_id: "r0", call_role: "finish", finish_reason: "stop" }, 3));
    const finalized = rounds["r0"];
    // A reordered/duplicated delta arriving after completion (e.g. WS replay overlap) must not append.
    rounds = reduceAgentRoundEvent(rounds, event("agent.round.delta", { round_id: "r0", channel: "assistant_content", text_delta: "追加内容" }, 4));
    expect(rounds["r0"]).toEqual(finalized);
    expect(rounds["r0"].content).toBe("已完成回答");

    let failedRounds = reduceAgentRoundEvent({}, event("agent.round.started", { round_id: "r1", index: 0, call_id: "c1" }));
    failedRounds = reduceAgentRoundEvent(failedRounds, event("agent.round.failed", { round_id: "r1", error_code: "provider_timeout" }, 2));
    failedRounds = reduceAgentRoundEvent(failedRounds, event("agent.round.delta", { round_id: "r1", channel: "assistant_content", text_delta: "迟到片段" }, 3));
    expect(failedRounds["r1"].content).toBe("");
  });
});

describe("buildTurnTrace", () => {
  it("orders each round before its own tools, then the next round", () => {
    const rounds = [
      { round_id: "r0", index: 0, call_id: "c0", status: "completed" as const, call_role: "narration" as const, public_summary: "", content: "", finish_reason: "tool_calls", error_code: null, retryable: false },
      { round_id: "r1", index: 1, call_id: "c1", status: "completed" as const, call_role: "finish" as const, public_summary: "", content: "", finish_reason: "stop", error_code: null, retryable: false },
    ];
    const tools = [
      tool({ tool_call_id: "k1", round_index: 0, call_index: 0 }),
      tool({ tool_call_id: "k2", round_index: 0, call_index: 1 }),
      tool({ tool_call_id: "k3", round_index: 1, call_index: 0 }),
    ];
    const nodes = buildTurnTrace(rounds, tools);
    const keys = nodes.map((n) => (n.kind === "round" ? `round:${n.round.round_id}` : `tool:${n.tool.tool_call_id}`));
    expect(keys).toEqual(["round:r0", "tool:k1", "tool:k2", "round:r1", "tool:k3"]);
  });

  it("accepts a map of rounds keyed by round id", () => {
    const rounds = { r0: { round_id: "r0", index: 0, call_id: "c0", status: "completed" as const, call_role: "finish" as const, public_summary: "", content: "", finish_reason: "stop", error_code: null, retryable: false } };
    const nodes = buildTurnTrace(rounds, [tool({ tool_call_id: "k1", round_index: 0, call_index: 0 })]);
    expect(nodes).toHaveLength(2);
    expect(nodes[0].kind).toBe("round");
    expect(nodes[1].kind).toBe("tool");
  });
});