import type { ChatBlockDTO } from "@/types/chat";

export interface ChatThreadWireDTO {
  thread_id: string;
  title: string;
  scenario: string;
  patient_id?: string | null;
  member_id?: number | null;
  is_deleted?: boolean;
  deleted_at?: string | null;
  updated_at?: string;
  server_updated_at?: string;
  image_delivery_mode?: string | null;
  icon_name?: string | null;
  icon_color_name?: string | null;
  is_pinned?: boolean;
  pinned_at?: string | null;
  current_model_name?: string | null;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  max_messages?: number | null;
  role_prompt?: string | null;
  system_prompt?: string | null;
}

export interface ChatMessageWireDTO {
  thread_id: string;
  role: "system" | "user" | "assistant";
  model_name?: string | null;
  client_message_id: string;
  server_message_id?: string | null;
  delivery_state: string;
  created_at: string;
  server_updated_at?: string | null;
  tombstone?: boolean;
  attachments?: unknown;
  blocks: ChatBlockDTO[];
  reasoning_content?: string | null;
  reasoning_duration_ms?: number | null;
  reasoning_expanded?: boolean;
  reasoning_visibility?: string | null;
}

export interface ThreadPullData {
  cursor: string | null;
  threads: ChatThreadWireDTO[];
  has_more: boolean;
}

export interface ThreadPushRequest {
  threads: ChatThreadWireDTO[];
}

export interface ThreadDeleteRequest {
  thread_ids: string[];
}

export interface MessagePullData {
  cursor: string | null;
  messages: ChatMessageWireDTO[];
  has_more: boolean;
}

export interface ThreadPushData {
  threads: ChatThreadWireDTO[];
}

export interface ThreadDeleteData {
  thread_ids: string[];
}
