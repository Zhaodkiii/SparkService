import type { ChatEventEnvelope } from "@/types/chat";
import type { ToolActivityDTO, ToolActivityStatus, ToolErrorDTO, ToolSourceRefDTO } from "@/types/tool";

/**
 * P4 tool activity reducer.
 *
 * `tool.call.requested` / `tool.result` / `tool.call.cancelled` events carry
 * the full safe activity projection; `tool.call.started` carries a partial
 * patch. All updates are revision-guarded: a stale replay can never regress a
 * tool call to an older status.
 */

export type ToolActivityMap = Record<string, ToolActivityDTO>;

const ACTIVITY_STATUSES: readonly ToolActivityStatus[] = ["requested", "running", "completed", "failed", "cancelled"];

export function asToolActivityStatus(value: unknown): ToolActivityStatus | null {
  return typeof value === "string" && (ACTIVITY_STATUSES as readonly string[]).includes(value)
    ? (value as ToolActivityStatus)
    : null;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function nullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function numberValue(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

/** Revision priority: requested(1) < running(2) < terminal(3). */
const STATUS_RANK: Record<ToolActivityStatus, number> = {
  requested: 1,
  running: 2,
  completed: 3,
  failed: 3,
  cancelled: 3,
};

function normalizeSourceRef(raw: unknown): ToolSourceRefDTO | null {
  const item = objectValue(raw);
  const sourceId = stringValue(item.source_id);
  if (!sourceId) return null;
  const ref: ToolSourceRefDTO = { source_id: sourceId, type: stringValue(item.type) || "unknown" };
  const title = nullableString(item.title);
  if (title) ref.title = title;
  return ref;
}

/**
 * Defensive normalization of the server activity projection. Unknown tools and
 * malformed payloads degrade to a generic "server tool" entry instead of
 * throwing, so one bad event can never break the whole chat runtime.
 */
export function normalizeToolActivity(raw: unknown): ToolActivityDTO | null {
  const item = objectValue(raw);
  const toolCallId = stringValue(item.tool_call_id);
  if (!toolCallId) return null;
  const status = asToolActivityStatus(item.status) ?? "requested";
  const rawError = objectValue(item.error);
  const error: ToolErrorDTO | null = rawError.code
    ? {
        code: stringValue(rawError.code),
        message_key: stringValue(rawError.message_key) || "tool_execution_failed",
        retryable: rawError.retryable === true,
      }
    : null;
  return {
    tool_call_id: toolCallId,
    name: stringValue(item.name) || "unknown_tool",
    version: stringValue(item.version) || "v1",
    display_name: stringValue(item.display_name) || "服务工具",
    target: "server",
    status,
    round_index: numberValue(item.round_index),
    call_index: numberValue(item.call_index),
    revision: numberValue(item.revision, 1),
    display_args: objectValue(item.display_args),
    result_preview: nullableString(item.result_preview),
    source_refs: Array.isArray(item.source_refs)
      ? item.source_refs.map(normalizeSourceRef).filter((ref): ref is ToolSourceRefDTO => ref !== null)
      : [],
    error,
    duplicate_of: nullableString(item.duplicate_of),
    started_at: nullableString(item.started_at),
    finished_at: nullableString(item.finished_at),
    progress_message: nullableString(item.progress_message),
    progress_percent: nullableNumber(item.progress_percent),
  };
}

/** Apply a full or partial activity update, honouring revision monotonicity. */
function mergeActivity(current: ToolActivityDTO | undefined, next: ToolActivityDTO): ToolActivityDTO {
  if (!current) return next;
  const currentRank = STATUS_RANK[current.status];
  const nextRank = STATUS_RANK[next.status];
  if (next.revision < current.revision) return current;
  if (next.revision === current.revision && nextRank <= currentRank) return current;
  return next;
}

export function reduceToolActivityEvent(map: ToolActivityMap, event: ChatEventEnvelope): ToolActivityMap {
  const payload = objectValue(event.payload);
  let next: ToolActivityDTO | null = null;
  if (event.type === "tool.call.requested" || event.type === "tool.result" || event.type === "tool.call.cancelled") {
    next = normalizeToolActivity(payload.activity);
  } else if (event.type === "tool.call.started") {
    // Partial patch: only meaningful when the requested projection exists.
    const current = map[payload.tool_call_id as string];
    if (!current) return map;
    next = normalizeToolActivity({
      ...current,
      status: payload.status ?? "running",
      revision: payload.revision ?? current.revision,
      started_at: payload.started_at ?? current.started_at,
    });
  } else if (event.type === "tool.call.progress") {
    // Partial progress patch: progress never regresses status or preview, so merge
    // the progress fields directly instead of going through the status-rank guard.
    const current = map[payload.tool_call_id as string];
    if (!current) return map;
    const progressMessage = nullableString(payload.progress_message);
    const progressPercent = nullableNumber(payload.progress_percent);
    const sameMessage = (progressMessage ?? current.progress_message ?? null) === (current.progress_message ?? null);
    const samePercent = (progressPercent ?? current.progress_percent ?? null) === (current.progress_percent ?? null);
    if (sameMessage && samePercent) return map;
    return {
      ...map,
      [current.tool_call_id]: {
        ...current,
        progress_message: progressMessage ?? current.progress_message,
        progress_percent: progressPercent ?? current.progress_percent,
      },
    };
  }
  if (!next) return map;
  const merged = mergeActivity(map[next.tool_call_id], next);
  if (merged === map[next.tool_call_id]) return map;
  return { ...map, [next.tool_call_id]: merged };
}

export function createInitialToolActivityMap(): ToolActivityMap {
  return {};
}

export const TOOL_ACTIVITY_EVENT_TYPES: readonly string[] = [
  "tool.call.requested",
  "tool.call.started",
  "tool.call.progress",
  "tool.result",
  "tool.call.cancelled",
];

export function isToolActivityEvent(type: string): boolean {
  return TOOL_ACTIVITY_EVENT_TYPES.includes(type);
}
