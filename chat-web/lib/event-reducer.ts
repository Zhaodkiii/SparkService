import {
  asRunStatus,
  type ChatBlockDTO,
  type ChatEventEnvelope,
  type ChatMessageDTO,
  type ChatRuntimeState,
} from "@/types/chat";
import { isToolActivityEvent, reduceToolActivityEvent } from "@/lib/tools/tool-activity-reducer";
import { isAgentRoundEvent, reduceAgentRoundEvent } from "@/lib/chat/turn-trace-reducer";
import { payloadKind } from "@/lib/chat/block-normalizer";
import { isInteractionEventType, type PendingInteractionDTO } from "@/types/interaction";

export function createInitialChatRuntimeState(): ChatRuntimeState {
  return {
    runsById: {},
    messagesById: {},
    blocksById: {},
    orderedBlockIdsByMessage: {},
    seenEventIdsByRun: {},
    lastAppliedSequenceByRun: {},
    bufferedEventsByRun: {},
    replayRequiredByRun: {},
    unknownActivitiesByRun: {},
    assistantStatusByRun: {},
    usageByRun: {},
    toolCallsByRun: {},
    roundsByRun: {},
    interactionsByRun: {},
  };
}

function payloadObject(event: ChatEventEnvelope): Record<string, unknown> {
  return event.payload && typeof event.payload === "object" ? event.payload : {};
}

function setSeen(state: ChatRuntimeState, event: ChatEventEnvelope): ChatRuntimeState {
  const seen = state.seenEventIdsByRun[event.run_id] ?? [];
  return { ...state, seenEventIdsByRun: { ...state.seenEventIdsByRun, [event.run_id]: [...seen, event.event_id] } };
}

function updateRun(state: ChatRuntimeState, event: ChatEventEnvelope, status: ChatRuntimeState["runsById"][string]["status"]): ChatRuntimeState {
  const payload = payloadObject(event);
  const current = state.runsById[event.run_id] ?? {
    id: event.run_id,
    thread_id: event.thread_id,
    status: "queued" as const,
    capability: "chat",
    last_sequence: 0,
  };
  const next = {
    ...current,
    status,
    thread_id: event.thread_id,
    last_sequence: Math.max(current.last_sequence, event.sequence),
    error: payload.error && typeof payload.error === "object" ? (payload.error as ChatRuntimeState["runsById"][string]["error"]) : current.error,
  };
  return { ...state, runsById: { ...state.runsById, [event.run_id]: next } };
}

function ensureMessage(state: ChatRuntimeState, messageId: string, role: ChatMessageDTO["role"] = "assistant"): ChatRuntimeState {
  if (state.messagesById[messageId]) return state;
  return {
    ...state,
    messagesById: { ...state.messagesById, [messageId]: { id: messageId, role, blocks: [] } },
    orderedBlockIdsByMessage: { ...state.orderedBlockIdsByMessage, [messageId]: [] },
  };
}

function applyBlockCreated(state: ChatRuntimeState, event: ChatEventEnvelope): ChatRuntimeState {
  const payload = payloadObject(event);
  const raw = payload.block && typeof payload.block === "object" ? payload.block as Partial<ChatBlockDTO> : payload;
  const blockId = String(raw.id ?? payload.block_id ?? "");
  if (!blockId) return state;
  const messageId = String(payload.message_id ?? "");
  let next = state;
  if (messageId) next = ensureMessage(next, messageId);
  const block: ChatBlockDTO = {
    id: blockId,
    // Live blocks use the same iOS tagged payload as sync; never infer a
    // second legacy shape from `kind`, otherwise malformed events render as
    // empty/"文本" cards instead of the contract error surface.
    kind: payloadKind(raw.payload) ?? "",
    status: (raw.status as ChatBlockDTO["status"]) ?? "pending",
    revision: Number(raw.revision ?? 0),
    order_key: typeof raw.order_key === "number" ? raw.order_key : null,
    node_role: String(raw.node_role ?? "timeline"),
    payload: (raw.payload as Record<string, unknown>) ?? {},
    tool_call_id: typeof raw.tool_call_id === "string" ? raw.tool_call_id : null,
    parent_tool_call_id: typeof raw.parent_tool_call_id === "string" ? raw.parent_tool_call_id : null,
    parent_block_id: typeof raw.parent_block_id === "string" ? raw.parent_block_id : null,
  };
  next = { ...next, blocksById: { ...next.blocksById, [blockId]: block } };
  if (messageId && !(next.orderedBlockIdsByMessage[messageId] ?? []).includes(blockId)) {
    const ids = [...(next.orderedBlockIdsByMessage[messageId] ?? []), blockId].sort((a, b) => Number(next.blocksById[a]?.order_key ?? 0) - Number(next.blocksById[b]?.order_key ?? 0));
    next = { ...next, orderedBlockIdsByMessage: { ...next.orderedBlockIdsByMessage, [messageId]: ids } };
  }
  return next;
}

function applyBlockUpdated(state: ChatRuntimeState, event: ChatEventEnvelope): ChatRuntimeState {
  // Full-block refresh (e.g. toolCall requested -> running -> terminal).
  const payload = payloadObject(event);
  const raw = payload.block && typeof payload.block === "object" ? payload.block as Partial<ChatBlockDTO> : null;
  const blockId = String(payload.block_id ?? raw?.id ?? "");
  const current = state.blocksById[blockId];
  if (!current) return state;
  const revision = Number(raw?.revision ?? payload.revision ?? current.revision);
  if (revision < current.revision) return state;
  const nextPayload = raw?.payload && typeof raw.payload === "object" ? raw.payload as Record<string, unknown> : current.payload;
  const status = typeof raw?.status === "string" && ["pending", "streaming", "ready", "failed"].includes(raw.status) ? raw.status : current.status;
  return { ...state, blocksById: { ...state.blocksById, [blockId]: { ...current, revision, status, payload: nextPayload } } };
}

function applyBlockDelta(state: ChatRuntimeState, event: ChatEventEnvelope): ChatRuntimeState {
  const payload = payloadObject(event);
  const blockId = String(payload.block_id ?? "");
  const current = state.blocksById[blockId];
  if (!current) return state;
  const revision = Number(payload.revision ?? current.revision);
  if (revision <= current.revision) return state;
  const delta = typeof payload.delta === "string" ? payload.delta : "";
  const currentPayload = current.payload;
  const textWrapper = currentPayload.text;
  let nextPayload: Record<string, unknown>;
  if (textWrapper && typeof textWrapper === "object" && !Array.isArray(textWrapper) && "_0" in textWrapper) {
    const prev = typeof (textWrapper as Record<string, unknown>)._0 === "string" ? (textWrapper as Record<string, unknown>)._0 : "";
    nextPayload = { ...currentPayload, text: { _0: prev + delta } };
  } else {
    const currentText = typeof textWrapper === "string" ? textWrapper : "";
    // Never recreate the legacy flat payload.  All live text must remain
    // iOS-compatible, even when a delta arrives before block.created.
    nextPayload = { text: { _0: currentText + delta } };
  }
  const block = { ...current, revision, status: "streaming" as const, payload: nextPayload };
  return { ...state, blocksById: { ...state.blocksById, [blockId]: block } };
}

function asInteraction(raw: unknown): PendingInteractionDTO | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const item = raw as Record<string, unknown>;
  const interactionId = typeof item.interaction_id === "string" ? item.interaction_id : "";
  const runId = typeof item.run_id === "string" ? item.run_id : "";
  if (!interactionId || !runId) return null;
  const request = item.request && typeof item.request === "object" && !Array.isArray(item.request) ? item.request as PendingInteractionDTO["request"] : {};
  return {
    run_id: runId,
    interaction_id: interactionId,
    interaction_key: typeof item.interaction_key === "string" ? item.interaction_key : "",
    kind: typeof item.kind === "string" ? item.kind : "ask_user",
    status: typeof item.status === "string" ? item.status : "pending",
    tool_call_id: typeof item.tool_call_id === "string" ? item.tool_call_id : null,
    tool_name: typeof item.tool_name === "string" ? item.tool_name : undefined,
    tool_version: typeof item.tool_version === "string" ? item.tool_version : undefined,
    schema_version: typeof item.schema_version === "number" ? item.schema_version : 1,
    question_ids: Array.isArray(item.question_ids) ? item.question_ids.map(String) : [],
    request,
    expires_at: typeof item.expires_at === "string" ? item.expires_at : null,
    result_summary: typeof item.result_summary === "string" ? item.result_summary : undefined,
    error_code: typeof item.error_code === "string" ? item.error_code : undefined,
  };
}

export function upsertInteractions(state: ChatRuntimeState, runId: string, items: PendingInteractionDTO[]): ChatRuntimeState {
  if (!runId || !items.length) return state;
  const current = { ...(state.interactionsByRun[runId] ?? {}) };
  let changed = false;
  for (const item of items) {
    if (!item.interaction_id) continue;
    current[item.interaction_id] = item;
    changed = true;
  }
  if (!changed) return state;
  return { ...state, interactionsByRun: { ...state.interactionsByRun, [runId]: current } };
}

function applyInteractionEvent(state: ChatRuntimeState, event: ChatEventEnvelope): ChatRuntimeState {
  const payload = payloadObject(event);
  const fromPayload = asInteraction(payload.interaction);
  const interactionId = fromPayload?.interaction_id || String(payload.interaction_id ?? "");
  const runId = fromPayload?.run_id || event.run_id;
  if (!interactionId || !runId) return state;
  const current = state.interactionsByRun[runId]?.[interactionId];
  const statusFromType: Record<string, PendingInteractionDTO["status"]> = {
    "interaction.requested": "pending",
    "interaction.resolved": "resolved",
    "interaction.refused": "refused",
    "interaction.expired": "expired",
    "interaction.cancelled": "cancelled",
    "interaction.claimed": "claimed",
  };
  const next: PendingInteractionDTO = {
    run_id: runId,
    interaction_id: interactionId,
    interaction_key: fromPayload?.interaction_key || current?.interaction_key || "",
    kind: fromPayload?.kind || current?.kind || "ask_user",
    status: fromPayload?.status || statusFromType[event.type] || current?.status || "pending",
    tool_call_id: fromPayload?.tool_call_id ?? current?.tool_call_id ?? null,
    tool_name: fromPayload?.tool_name ?? current?.tool_name,
    tool_version: fromPayload?.tool_version ?? current?.tool_version,
    schema_version: fromPayload?.schema_version ?? current?.schema_version ?? 1,
    question_ids: fromPayload?.question_ids?.length ? fromPayload.question_ids : current?.question_ids ?? [],
    request: fromPayload?.request && Object.keys(fromPayload.request).length ? fromPayload.request : current?.request ?? {},
    expires_at: fromPayload?.expires_at ?? current?.expires_at ?? null,
    result_summary: fromPayload?.result_summary ?? current?.result_summary,
    error_code: fromPayload?.error_code ?? (typeof payload.reason_code === "string" ? payload.reason_code : current?.error_code),
  };
  return upsertInteractions(state, runId, [next]);
}

function applyOne(state: ChatRuntimeState, event: ChatEventEnvelope): ChatRuntimeState {
  const payload = payloadObject(event);
  let next = setSeen(state, event);
  const last = Math.max(next.lastAppliedSequenceByRun[event.run_id] ?? 0, event.sequence);
  next = { ...next, lastAppliedSequenceByRun: { ...next.lastAppliedSequenceByRun, [event.run_id]: last } };
  if (event.type === "run.queued") next = updateRun(next, event, "queued");
  else if (event.type === "run.started") next = updateRun(next, event, "running");
  else if (event.type === "run.waiting") {
    const waiting = asRunStatus(payload.status);
    if (waiting === "waiting_for_user_input" || waiting === "waiting_for_client_tool") next = updateRun(next, event, waiting);
  }
  else if (event.type === "run.resumed") next = updateRun(next, event, "queued");
  else if (event.type === "run.waiting_for_user_input") next = updateRun(next, event, "waiting_for_user_input");
  else if (event.type === "run.waiting_for_client_tool") next = updateRun(next, event, "waiting_for_client_tool");
  else if (event.type === "run.completed") next = updateRun(next, event, "completed");
  else if (event.type === "run.failed") next = updateRun(next, event, "failed");
  else if (event.type === "run.cancelled") next = updateRun(next, event, "cancelled");
  else if (event.type === "run.interrupted") next = updateRun(next, event, "interrupted");
  else if (event.type === "block.created") next = applyBlockCreated(next, event);
  else if (event.type === "block.updated") next = applyBlockUpdated(next, event);
  else if (event.type === "block.delta") next = applyBlockDelta(next, event);
  else if (event.type === "assistant.status") {
    const status = String(payload.status ?? payload.state ?? "thinking");
    next = { ...next, assistantStatusByRun: { ...next.assistantStatusByRun, [event.run_id]: status } };
  }
  else if (event.type === "usage.final") next = { ...next, usageByRun: { ...next.usageByRun, [event.run_id]: payload } };
  else if (event.type === "usage.updated") {
    const current = next.usageByRun[event.run_id] ?? {};
    next = { ...next, usageByRun: { ...next.usageByRun, [event.run_id]: { ...current, ...payload } } };
  }
  else if (isAgentRoundEvent(event.type)) {
    const map = next.roundsByRun[event.run_id] ?? {};
    const updated = reduceAgentRoundEvent(map, event);
    if (updated !== map) next = { ...next, roundsByRun: { ...next.roundsByRun, [event.run_id]: updated } };
  }
  else if (isToolActivityEvent(event.type)) {
    const map = next.toolCallsByRun[event.run_id] ?? {};
    const updated = reduceToolActivityEvent(map, event);
    if (updated !== map) next = { ...next, toolCallsByRun: { ...next.toolCallsByRun, [event.run_id]: updated } };
  }
  else if (isInteractionEventType(event.type)) {
    next = applyInteractionEvent(next, event);
  }
  else if (event.type === "block.completed") {
    const blockId = String(payload.block_id ?? "");
    const block = next.blocksById[blockId];
    if (block && Number(payload.revision ?? block.revision) >= block.revision) next = { ...next, blocksById: { ...next.blocksById, [blockId]: { ...block, revision: Number(payload.revision ?? block.revision), status: "ready" } } };
  } else if (event.type === "block.failed") {
    const blockId = String(payload.block_id ?? "");
    const block = next.blocksById[blockId];
    if (block && Number(payload.revision ?? block.revision) >= block.revision) next = { ...next, blocksById: { ...next.blocksById, [blockId]: { ...block, revision: Number(payload.revision ?? block.revision), status: "failed" } } };
  } else if (event.type === "run.done") {
    const current = next.runsById[event.run_id];
    if (current) next = updateRun(next, event, current.status);
  } else {
    const activities = next.unknownActivitiesByRun[event.run_id] ?? [];
    next = { ...next, unknownActivitiesByRun: { ...next.unknownActivitiesByRun, [event.run_id]: [...activities, event] } };
  }
  return next;
}

export function reduceChatEvent(state: ChatRuntimeState, event: ChatEventEnvelope): ChatRuntimeState {
  if (!event?.run_id || !event.event_id || !Number.isInteger(event.sequence) || event.sequence < 1) return state;
  const seen = state.seenEventIdsByRun[event.run_id] ?? [];
  if (seen.includes(event.event_id)) return state;
  const last = state.lastAppliedSequenceByRun[event.run_id] ?? 0;
  if (event.sequence <= last) return state;
  if (event.sequence > last + 1) {
    const buffer = [...(state.bufferedEventsByRun[event.run_id] ?? []), event].sort((a, b) => a.sequence - b.sequence);
    return { ...state, bufferedEventsByRun: { ...state.bufferedEventsByRun, [event.run_id]: buffer }, replayRequiredByRun: { ...state.replayRequiredByRun, [event.run_id]: true } };
  }
  let next = applyOne(state, event);
  let buffer = [...(next.bufferedEventsByRun[event.run_id] ?? [])];
  while (buffer.length && buffer[0].sequence === (next.lastAppliedSequenceByRun[event.run_id] ?? 0) + 1) {
    const [candidate, ...rest] = buffer;
    next = applyOne(next, candidate);
    buffer = rest;
  }
  return { ...next, bufferedEventsByRun: { ...next.bufferedEventsByRun, [event.run_id]: buffer }, replayRequiredByRun: { ...next.replayRequiredByRun, [event.run_id]: buffer.length > 0 } };
}

export function reduceChatEvents(state: ChatRuntimeState, events: ChatEventEnvelope[]): ChatRuntimeState {
  return events.reduce(reduceChatEvent, state);
}

export function runStatusLabel(status: ChatRuntimeState["runsById"][string]["status"]): string {
  return { queued: "排队中", running: "运行中", waiting_for_user_input: "等待你的回复", waiting_for_client_tool: "等待设备授权", completed: "已完成", failed: "生成失败", cancelled: "已停止", interrupted: "已中断", unknown: "需要更新版本" }[status];
}
