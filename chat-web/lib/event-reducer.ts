import {
  asRunStatus,
  type ChatBlockDTO,
  type ChatEventEnvelope,
  type ChatMessageDTO,
  type ChatRuntimeState,
} from "@/types/chat";

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
    kind: String(raw.kind ?? "text"),
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

function applyBlockDelta(state: ChatRuntimeState, event: ChatEventEnvelope): ChatRuntimeState {
  const payload = payloadObject(event);
  const blockId = String(payload.block_id ?? "");
  const current = state.blocksById[blockId];
  if (!current) return state;
  const revision = Number(payload.revision ?? current.revision);
  if (revision <= current.revision) return state;
  const delta = typeof payload.delta === "string" ? payload.delta : "";
  const currentText = typeof current.payload.text === "string" ? current.payload.text : "";
  const block = { ...current, revision, status: "streaming" as const, payload: { ...current.payload, text: currentText + delta, content_type: payload.content_type ?? current.payload.content_type ?? "text/markdown" } };
  return { ...state, blocksById: { ...state.blocksById, [blockId]: block } };
}

function applyOne(state: ChatRuntimeState, event: ChatEventEnvelope): ChatRuntimeState {
  const payload = payloadObject(event);
  let next = setSeen(state, event);
  const last = Math.max(next.lastAppliedSequenceByRun[event.run_id] ?? 0, event.sequence);
  next = { ...next, lastAppliedSequenceByRun: { ...next.lastAppliedSequenceByRun, [event.run_id]: last } };
  if (event.type === "run.queued") next = updateRun(next, event, "queued");
  else if (event.type === "run.started") next = updateRun(next, event, "running");
  else if (event.type === "run.waiting_for_user_input") next = updateRun(next, event, "waiting_for_user_input");
  else if (event.type === "run.waiting_for_client_tool") next = updateRun(next, event, "waiting_for_client_tool");
  else if (event.type === "run.completed") next = updateRun(next, event, "completed");
  else if (event.type === "run.failed") next = updateRun(next, event, "failed");
  else if (event.type === "run.cancelled") next = updateRun(next, event, "cancelled");
  else if (event.type === "run.interrupted") next = updateRun(next, event, "interrupted");
  else if (event.type === "block.created") next = applyBlockCreated(next, event);
  else if (event.type === "block.delta") next = applyBlockDelta(next, event);
  else if (event.type === "assistant.status") {
    const status = String(payload.status ?? payload.state ?? "thinking");
    next = { ...next, assistantStatusByRun: { ...next.assistantStatusByRun, [event.run_id]: status } };
  }
  else if (event.type === "usage.final") next = { ...next, usageByRun: { ...next.usageByRun, [event.run_id]: payload } };
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
  return { queued: "排队中", running: "运行中", waiting_for_user_input: "等待你的回复", waiting_for_client_tool: "等待设备授权", completed: "已完成", failed: "生成失败", cancelled: "已取消", interrupted: "已中断", unknown: "需要更新版本" }[status];
}
