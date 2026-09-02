import type { ToolActivityDTO } from "@/types/tool";
import type { PendingInteractionDTO } from "@/types/interaction";

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

/**
 * Canonical block kinds, aligned with the iOS `ChatMessageBlock.Kind` Swift
 * enum (37 case names). `toolCall`/`toolResult` are intentionally absent here:
 * they are browser-internal projections produced by the P4 tool activity loop,
 * not canonical wire kinds (see `WebToolActivityBlockKind`).
 */
export type ChatBlockKind =
  | "text"
  | "deepThought"
  | "tool"
  | "imageGallery"
  | "fileAttachments"
  | "knowledgeCards"
  | "translatedText"
  | "mapRoute"
  | "events"
  | "healthCards"
  | "pendingMemberToolCards"
  | "toolQuestionCards"
  | "toolMemberSelectionCards"
  | "healthResourceCandidateCards"
  | "toolConsentCards"
  | "locationPermissionCards"
  | "structuredHealthCards"
  | "sleepVisualization"
  | "stepVisualization"
  | "energyVisualization"
  | "nutritionReadVisualization"
  | "weatherVisualization"
  | "weatherConfigCard"
  | "searchSummary"
  | "nutritionCards"
  | "workoutVisualization"
  | "captureCard"
  | "html"
  | "smallTaskCard"
  | "taskCards"
  | "error"
  | "assistantStatusCard"
  | "healthResourceReference"
  | "medicalRiskNotice"
  | "medicalDisclaimerCard"
  | "chatGuideCard"
  | "hospitalDoctorIntroCard";

/**
 * Browser-internal projection kind produced by the P4 tool activity loop from
 * `tool.call.*` / `tool.result.*` Run Events. Not a canonical
 * `ChatMessageBlock.Kind`, so it is kept out of `ChatBlockKind`.
 */
export type WebToolActivityBlockKind = "toolCall" | "toolResult";

export const CHAT_BLOCK_KINDS: readonly ChatBlockKind[] = [
  "text", "deepThought", "tool", "imageGallery", "fileAttachments", "knowledgeCards",
  "translatedText", "mapRoute", "events", "healthCards", "pendingMemberToolCards",
  "toolQuestionCards", "toolMemberSelectionCards", "healthResourceCandidateCards",
  "toolConsentCards", "locationPermissionCards", "structuredHealthCards",
  "sleepVisualization", "stepVisualization", "energyVisualization",
  "nutritionReadVisualization", "weatherVisualization", "weatherConfigCard",
  "searchSummary", "nutritionCards", "workoutVisualization", "captureCard", "html",
  "smallTaskCard", "taskCards", "error", "assistantStatusCard",
  "healthResourceReference", "medicalRiskNotice", "medicalDisclaimerCard", "chatGuideCard",
  "hospitalDoctorIntroCard",
];

export const WEB_TOOL_ACTIVITY_BLOCK_KINDS: readonly WebToolActivityBlockKind[] = ["toolCall", "toolResult"];

export type ChatNodeRole = "timeline" | "tool" | "toolPresentation";

/** iOS `ChatBlockAnchor` union.  Only beforeBlock/afterBlock/toolCall carry a value. */
export type ChatBlockAnchor =
  | { type: "messageStart" }
  | { type: "messageEnd" }
  | { type: "beforeBlock"; value: string }
  | { type: "afterBlock"; value: string }
  | { type: "toolCall"; value: string };

export interface ChatUsageSummary {
  model: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  reasoning_tokens: number;
  model_calls: number;
  tool_calls: number;
}

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
  order_key: number | string | null;
  tool_call_id?: string | null;
  parent_tool_call_id?: string | null;
  parent_block_id?: string | null;
  node_role: string;
  anchor?: ChatBlockAnchor | null;
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
  /** P4 safe tool activity projections, keyed by run id then tool_call_id. */
  toolCallsByRun: Record<string, Record<string, ToolActivityDTO>>;
  /** Public agent round traces, keyed by run id then round_id. */
  roundsByRun: Record<string, Record<string, AgentRoundTraceDTO>>;
  /** Pending ask_user / client-tool interactions keyed by run id then interaction_id. */
  interactionsByRun: Record<string, Record<string, PendingInteractionDTO>>;
}

/** Turn-level activity phase, derived from run/tool/content signals. */
export type TurnActivityPhase =
  | "exploring"
  | "using_tools"
  | "composing"
  | "waiting"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted";

/**
 * Sanitized turn activity view model (能力二公开投影). Only public status,
 * phase and tool rows reach the UI; raw reasoning, arguments and results are
 * never carried by this type.
 */
export interface TurnActivityViewModel {
  runId: string | null;
  runStatus: ChatRunStatus | null;
  phase: TurnActivityPhase;
  publicStatusLabel: string;
  toolRows: ToolActivityDTO[];
  hasToolActivity: boolean;
  anyToolRunning: boolean;
  isRunning: boolean;
  isTerminal: boolean;
  isFinalAnswerPhase: boolean;
  autoExpanded: boolean;
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

/**
 * 能力二/三：公开 Agent Round 轨迹投影。只承载公开 reasoning summary 与
 * narration 文本；隐藏 CoT 永不进入该结构。由 `agent.round.*` 事件增量归一化。
 */
export type AgentRoundStatus = "running" | "completed" | "failed";

export type AgentRoundCallRole = "narration" | "finish";

export interface AgentRoundTraceDTO {
  round_id: string;
  index: number;
  call_id: string;
  status: AgentRoundStatus;
  call_role: AgentRoundCallRole | null;
  /** 公开 reasoning 摘要增量（channel=public_reasoning_summary）。 */
  public_summary: string;
  /** 本轮候选正文（工具轮为 narration，无工具轮为 finish）。 */
  content: string;
  finish_reason: string | null;
  error_code: string | null;
  retryable: boolean;
}

/**
 * 回合用量摘要（能力五）：费用仅在 `amount`/`currency`/`price_version`
 * 同时存在可靠计价来源时才展示，否则只展示 Token 与调用次数。
 */
export interface TurnUsageSummary {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  reasoning_tokens: number | null;
  tool_calls: number | null;
  model_calls: number | null;
  amount: string | null;
  currency: string | null;
  price_version: string | null;
}

/** Sync 消息的安全公开回合摘要，驱动回合操作权限与用量展示。 */
export interface TurnSummary {
  run_id: string | null;
  status: ChatRunStatus | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  regenerate_allowed: boolean;
  delete_allowed: boolean;
  usage: TurnUsageSummary | null;
}

export interface TurnTraceRoundNode {
  kind: "round";
  round: AgentRoundTraceDTO;
}

export interface TurnTraceToolNode {
  kind: "tool";
  tool: ToolActivityDTO;
}

export type TurnTraceNode = TurnTraceRoundNode | TurnTraceToolNode;

/** 回合操作权限投影，依赖稳定的 run/message 归属。 */
export interface TurnActionPermissions {
  regenerateAllowed: boolean;
  deleteAllowed: boolean;
}
