import type { ChatRunDTO } from "@/types/chat";
import type { ChatEventEnvelope } from "@/types/chat";

export interface CreateRunRequestDTO {
  client_message_id: string;
  content?: string;
  capability: "chat";
  preferences_revision?: number | null;
  context_parent_message_id?: number | null;
  references: unknown[];
  attachments: unknown[];
  client: {
    platform: "web";
    version: string;
    device_id: string;
  };
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
