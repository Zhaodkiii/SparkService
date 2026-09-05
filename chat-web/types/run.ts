import type { ChatRunDTO } from "@/types/chat";
import type { ChatEventEnvelope } from "@/types/chat";

/**
 * Canonical Create Run v2 request: the user turn is carried as a canonical
 * `input_message` (iOS ChatMessage shape) and the run command in `run_options`.
 * The legacy `content` flat path is no longer emitted by the Web client.
 */
export interface CanonicalInputBlockDTO {
  id?: string;
  kind: string;
  status?: "pending" | "streaming" | "ready" | "failed";
  revision?: number;
  order_key?: number | null;
  tool_call_id?: string | null;
  parent_tool_call_id?: string | null;
  parent_block_id?: string | null;
  node_role?: string;
  anchor?: unknown;
  payload: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface CanonicalInputMessageDTO {
  thread_id: string;
  role: "user";
  client_message_id: string;
  server_message_id?: string | null;
  delivery_state?: string;
  created_at?: string;
  tombstone?: boolean;
  model_name?: string | null;
  blocks: CanonicalInputBlockDTO[];
}

/**
 * 图片附件（CHAT-WEB-029）：CreateRun `run_options.attachments` 中的图片项。
 * `file_id` 是服务端事实来源，`display_url` 只用于展示。
 */
export interface ChatImageAttachmentDTO {
  /** iOS ChatAttachment.id（必填 UUID）；取 ManagedFile.file_uuid。 */
  id?: string;
  file_id: string;
  type: "image";
  order: number;
  mime_type?: string;
  file_size?: number;
  display_url?: string;
}

/** CreateRun 附件：上下文文件引用或图片附件。 */
export type RunAttachmentDTO = { file_id: string } | ChatImageAttachmentDTO;

export interface RunOptionsDTO {
  capability: "chat";
  preferences_revision?: number | null;
  context_parent_message_id?: number | null;
  context_inputs: unknown[];
  attachments: RunAttachmentDTO[];
  client: {
    platform: "web";
    version: string;
    device_id: string;
  };
}

export interface CreateRunRequestDTO {
  input_message: CanonicalInputMessageDTO;
  run_options: RunOptionsDTO;
}

export interface ContextSummarySourceDTO {
  source_id: string;
  type: string;
  title: string;
  availability: "available" | "metadata_only" | "unavailable";
}

export interface ContextSummaryDTO {
  run_id: string;
  build_status: "pending" | "building" | "ready" | "degraded" | "failed";
  preferences_revision: number | null;
  language: string;
  history: { selected_count: number; trimmed: boolean; summary_used: boolean };
  budget_level: "normal" | "near_limit" | "exceeded";
  sources: ContextSummarySourceDTO[];
}

export interface RunSubscriptionDTO {
  websocket_path: string;
  resume_after_sequence: number;
}

export interface CreateRunData {
  run: ChatRunDTO;
  subscription: RunSubscriptionDTO;
}

export interface RunEventsData {
  events: ChatEventEnvelope[];
  next_after_sequence: number;
  has_more: boolean;
}

export interface WebSocketTicketData {
  ticket: string;
  expires_in: number;
  websocket_path: string;
}

export interface ChatRunReadinessDTO {
  available: boolean;
  code: string;
  retryable: boolean;
  checked_at: string | null;
  executor: string;
  model_binding_configured: boolean;
  worker_healthy: boolean;
  config_version: string | null;
  /** 当前模型是否支持图片理解（CHAT-WEB-029）；缺失/异常一律视为不支持。 */
  supports_image_input?: boolean;
}
