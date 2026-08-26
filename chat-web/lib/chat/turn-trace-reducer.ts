import type { AgentRoundCallRole, AgentRoundStatus, AgentRoundTraceDTO, ChatEventEnvelope, TurnTraceNode } from "@/types/chat";
import type { ToolActivityDTO } from "@/types/tool";

/**
 * 能力二/三/五：把 `agent.round.*` 事件增量归一化成分轮的公开轨迹，再把
 * Round 与工具活动合并成用户侧可读的有序 Trace。隐藏 CoT 与工具原始参数
 * 永不进入此投影。
 */

export type AgentRoundMap = Record<string, AgentRoundTraceDTO>;

const ROUND_EVENT_TYPES: readonly string[] = [
  "agent.round.started",
  "agent.round.delta",
  "agent.round.completed",
  "agent.round.failed",
];

export function isAgentRoundEvent(type: string): boolean {
  return ROUND_EVENT_TYPES.includes(type);
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function asRoundStatus(value: unknown): AgentRoundStatus {
  return value === "completed" || value === "failed" ? value : "running";
}

function asCallRole(value: unknown): AgentRoundCallRole | null {
  return value === "narration" || value === "finish" ? value : null;
}

/** 首包归一化：未知/畸形事件降级为通用 running 轮，绝不抛错。 */
function normalizeStarted(payload: Record<string, unknown>): AgentRoundTraceDTO | null {
  const roundId = stringValue(payload.round_id);
  if (!roundId) return null;
  return {
    round_id: roundId,
    index: numberValue(payload.index),
    call_id: stringValue(payload.call_id),
    status: "running",
    call_role: null,
    public_summary: "",
    content: "",
    finish_reason: null,
    error_code: null,
    retryable: false,
  };
}

export function reduceAgentRoundEvent(rounds: AgentRoundMap, event: ChatEventEnvelope): AgentRoundMap {
  const payload = objectValue(event.payload);
  const roundId = stringValue(payload.round_id);
  if (!roundId) return rounds;
  const current = rounds[roundId];
  if (event.type === "agent.round.started") {
    if (current) return rounds;
    const next = normalizeStarted(payload);
    if (!next) return rounds;
    return { ...rounds, [roundId]: next };
  }
  if (!current) return rounds;
  if (event.type === "agent.round.delta") {
    // CHAT-WEB-027: mirrors the backend round_runner "no rollback once
    // classified" rule — a late delta replayed/reordered after the round
    // already reached a terminal status must never mutate the finalized
    // public_summary/content the UI already committed to.
    if (current.status !== "running") return rounds;
    const channel = stringValue(payload.channel);
    const delta = stringValue(payload.text_delta);
    if (!delta) return rounds;
    if (channel === "public_reasoning_summary") {
      return { ...rounds, [roundId]: { ...current, public_summary: current.public_summary + delta } };
    }
    if (channel === "assistant_content") {
      return { ...rounds, [roundId]: { ...current, content: current.content + delta } };
    }
    return rounds;
  }
  if (event.type === "agent.round.completed") {
    return {
      ...rounds,
      [roundId]: {
        ...current,
        status: "completed",
        call_role: asCallRole(payload.call_role),
        finish_reason: stringValue(payload.finish_reason) || null,
      },
    };
  }
  if (event.type === "agent.round.failed") {
    return {
      ...rounds,
      [roundId]: {
        ...current,
        status: "failed",
        error_code: stringValue(payload.error_code) || "round_failed",
        retryable: payload.retryable === true,
      },
    };
  }
  return rounds;
}

export function reduceAgentRoundEvents(rounds: AgentRoundMap, events: ChatEventEnvelope[]): AgentRoundMap {
  return events.reduce(reduceAgentRoundEvent, rounds);
}

/**
 * 把 Round 与工具活动按轮次合并成用户可见的有序轨迹：
 * 同一轮内 Round 在前、工具按 call_index 在后，之后进入下一轮。
 */
export function buildTurnTrace(
  rounds: AgentRoundMap | AgentRoundTraceDTO[] | null | undefined,
  toolRows: ToolActivityDTO[],
): TurnTraceNode[] {
  const roundList = Array.isArray(rounds) ? rounds : Object.values(rounds ?? {});
  const nodes: TurnTraceNode[] = [
    ...roundList.map((round): TurnTraceNode => ({ kind: "round", round })),
    ...toolRows.map((tool): TurnTraceNode => ({ kind: "tool", tool })),
  ];
  const sortKey = (node: TurnTraceNode) => {
    const index = node.kind === "round" ? node.round.index : node.tool.round_index;
    const rank = node.kind === "round" ? 0 : 1;
    const callIndex = node.kind === "tool" ? node.tool.call_index : 0;
    const id = node.kind === "round" ? node.round.round_id : node.tool.tool_call_id;
    return { index, rank, callIndex, id };
  };
  return nodes.sort((a, b) => {
    const ka = sortKey(a);
    const kb = sortKey(b);
    return ka.index - kb.index || ka.rank - kb.rank || ka.callIndex - kb.callIndex || ka.id.localeCompare(kb.id);
  });
}