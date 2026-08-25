export type ChatRunStatus =
  | "queued"
  | "running"
  | "waiting_for_user_input"
  | "waiting_for_client_tool"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted"
  | "unknown";

export type ChatBlockStatus = "pending" | "streaming" | "ready" | "failed";

export interface ChatRunDTO {
  id: string;
  thread_id: string;
  status: ChatRunStatus;
  capability: string;
  capability_version?: string | null;
  user_message_id?: number | string | null;
  assistant_message_id?: number | string | null;
  last_sequence: number;
  error?: { code: string; message: string; retryable?: boolean } | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface ChatEventEnvelope<TPayload = Record<string, unknown>> {
  type: string;
  event_id: string;
  payload_version: number;
  run_id: string;
  thread_id: string;
  sequence: number;
  timestamp: string;
  payload: TPayload;
}

export interface ChatBlockDTO {
  id: string;
  kind: string;
  status: ChatBlockStatus;
  revision: number;
  order_key: number | null;
  tool_call_id?: string | null;
  parent_tool_call_id?: string | null;
  parent_block_id?: string | null;
  node_role: string;
  anchor?: Record<string, unknown> | null;
  payload: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface ChatMessageDTO {
  id: string;
  role: "user" | "assistant" | "system";
  blocks: string[];
  created_at?: string;
}

export interface ChatRuntimeState {
  runsById: Record<string, ChatRunDTO>;
  messagesById: Record<string, ChatMessageDTO>;
  blocksById: Record<string, ChatBlockDTO>;
  orderedBlockIdsByMessage: Record<string, string[]>;
  seenEventIdsByRun: Record<string, string[]>;
  lastAppliedSequenceByRun: Record<string, number>;
  bufferedEventsByRun: Record<string, ChatEventEnvelope[]>;
  replayRequiredByRun: Record<string, boolean>;
  unknownActivitiesByRun: Record<string, ChatEventEnvelope[]>;
  assistantStatusByRun: Record<string, string>;
  usageByRun: Record<string, Record<string, unknown>>;
}

export const TERMINAL_RUN_STATUSES: ReadonlySet<ChatRunStatus> = new Set([
  "completed",
  "failed",
  "cancelled",
  "interrupted",
]);

export function isTerminalRunStatus(status: ChatRunStatus): boolean {
  return TERMINAL_RUN_STATUSES.has(status);
}

export function asRunStatus(value: unknown): ChatRunStatus {
  const statuses: ChatRunStatus[] = [
    "queued",
    "running",
    "waiting_for_user_input",
    "waiting_for_client_tool",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
  ];
  return typeof value === "string" && statuses.includes(value as ChatRunStatus)
    ? (value as ChatRunStatus)
    : "unknown";
}
