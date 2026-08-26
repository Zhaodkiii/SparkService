/**
 * P4 Server Agentic Tool contract types.
 *
 * These mirror the server-side public projection exactly:
 * every field here is produced by `chat_sync.ai_runtime.tools.public_projector`
 * and `chat_sync.ai_services.tool_catalog_service`. Raw arguments, raw tool
 * results, internal hashes and execution keys are never part of this wire
 * format — never extend these types with such fields.
 */

export type ToolTarget = "server";

export type ToolActivityStatus =
  | "requested"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export const TERMINAL_TOOL_ACTIVITY_STATUSES: ReadonlySet<ToolActivityStatus> = new Set([
  "completed",
  "failed",
  "cancelled",
]);

export function isTerminalToolActivityStatus(status: ToolActivityStatus): boolean {
  return TERMINAL_TOOL_ACTIVITY_STATUSES.has(status);
}

/** Public error projection: safe code + message key, never raw error text. */
export interface ToolErrorDTO {
  code: string;
  message_key: string;
  retryable: boolean;
}

/** Allow-listed source reference: no URLs, no content hashes, no extras. */
export interface ToolSourceRefDTO {
  source_id: string;
  type: string;
  title?: string;
}

/**
 * Safe tool activity projection carried by `tool.call.requested`,
 * `tool.result` and `tool.call.cancelled` events.
 */
export interface ToolActivityDTO {
  tool_call_id: string;
  name: string;
  version: string;
  display_name: string;
  target: ToolTarget;
  status: ToolActivityStatus;
  round_index: number;
  call_index: number;
  revision: number;
  display_args: Record<string, unknown>;
  result_preview: string | null;
  source_refs: ToolSourceRefDTO[];
  error: ToolErrorDTO | null;
  duplicate_of: string | null;
  started_at: string | null;
  finished_at: string | null;
  /** 公开进度摘要，仅百分比/阶段文案，不含 raw stdout 或敏感数据。 */
  progress_message?: string | null;
  progress_percent?: number | null;
}

export type ToolUnavailableReason =
  | "feature_disabled"
  | "model_unsupported"
  | "member_required"
  | "source_required";

/** One entry of the per-thread public tool catalog (GET /threads/:id/tools/). */
export interface ToolCatalogItemDTO {
  name: string;
  version: string;
  display_name: string;
  description: string;
  target: ToolTarget;
  risk: "read_only";
  enabled: boolean;
  available: boolean;
  unavailable_reason: ToolUnavailableReason | null;
  requires: string[];
}

export interface ToolCatalogDTO {
  catalog_revision: string;
  preferences_revision: number;
  tools: ToolCatalogItemDTO[];
}

/** PATCH /threads/:id/preferences/ (partial; revision guards optimistic locking). */
export interface ThreadPreferencesUpdateDTO {
  enabled_tools?: string[];
  language?: string;
}

export interface ThreadPreferencesDTO extends ThreadPreferencesUpdateDTO {
  revision: number;
  capability?: string;
  enabled_tools?: string[];
  knowledge_bases?: string[];
}
