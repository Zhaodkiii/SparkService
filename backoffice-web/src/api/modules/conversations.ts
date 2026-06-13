import http from '../http';
import type { AxiosRequestConfig } from 'axios';
import type { Pagination } from '../../types';

type RequestConfig = AxiosRequestConfig & { signal?: AbortSignal };

export interface ConversationUserStats {
  user_count: number;
  thread_count: number;
  message_count: number;
  user_message_count: number;
  assistant_message_count: number;
  deleted_thread_count: number;
}

export interface ConversationUserRow {
  user_id: number;
  username: string;
  raw_username: string;
  email: string;
  is_active: boolean;
  user_status: string;
  is_anonymized: boolean;
  thread_count: number;
  active_thread_count: number;
  deleted_thread_count: number;
  message_count: number;
  tombstone_count: number;
  user_message_count: number;
  assistant_message_count: number;
  last_conversation_at: string | null;
  last_thread_id: string | null;
  last_thread_title: string;
  last_model_name: string;
  date_joined: string | null;
}

export interface ConversationUserListResponse {
  items: ConversationUserRow[];
  stats: ConversationUserStats;
  pagination: Pagination;
}

export interface ConversationUserSummary {
  user: {
    user_id: number;
    username: string;
    raw_username: string;
    email: string;
    is_active: boolean;
    user_status: string;
    is_anonymized: boolean;
    date_joined: string | null;
  };
  stats: {
    thread_count: number;
    deleted_thread_count: number;
    message_count: number;
    tombstone_count: number;
    user_message_count: number;
    assistant_message_count: number;
    last_conversation_at: string | null;
    medical_block_count: number;
    heavy_block_count: number;
    attachment_count: number;
    last_medical_resource_at: string | null;
  };
  model_distribution: Array<{ model_name: string; count: number }>;
  recent_7_day_trend: Array<{ date: string; message_count: number }>;
}

export interface ConversationThreadRow {
  thread_id: string;
  title: string;
  scenario: string;
  current_model_name: string | null;
  patient_id: string | null;
  member_id: number | null;
  temperature: number | null;
  top_p: number | null;
  max_tokens: number | null;
  max_messages: number | null;
  role_prompt: string;
  image_delivery_mode: string | null;
  is_pinned: boolean;
  is_deleted: boolean;
  deleted_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  server_updated_at: string | null;
  message_count: number;
  tombstone_count: number;
  user_message_count: number;
  assistant_message_count: number;
  last_message_at: string | null;
  has_tool: boolean;
  has_attachment: boolean;
  has_failed_message: boolean;
  block_kinds: string[];
  message_preview: string;
  medical_block_count: number;
  heavy_block_count: number;
  attachment_count: number;
  last_medical_resource_at: string | null;
}

export interface ConversationBlock {
  id: string;
  kind: string;
  resolved_kind?: string;
  status: string;
  revision: number;
  order_key: number | null;
  tool_call_id: string | null;
  parent_tool_call_id: string | null;
  parent_block_id: string | null;
  node_role: string;
  anchor: unknown;
  payload: Record<string, unknown> | null;
  block_summary: string;
  has_heavy_detail?: boolean;
  detail_load_mode?: 'inline' | 'lazy';
  detail_endpoint?: string | null;
  detail_status?: 'not_loaded' | 'loaded' | 'failed';
  created_at: string | null;
  updated_at: string | null;
  is_virtual?: boolean;
}

export interface ConversationMessage {
  message_db_id: number;
  thread_id: string;
  role: 'system' | 'user' | 'assistant';
  model_name: string | null;
  client_message_id: string;
  server_message_id: string | null;
  delivery_state: string;
  tombstone: boolean;
  created_at: string | null;
  server_updated_at: string | null;
  blocks: ConversationBlock[];
  blocks_count: number;
  block_kinds: string[];
  message_preview: string;
  metadata: Record<string, unknown>;
  debug_endpoint?: string;
  raw?: Record<string, unknown>;
}

export interface ConversationMessageDebug {
  message_db_id: number;
  thread_id: string;
  role: string;
  model_name: string | null;
  client_message_id: string;
  server_message_id: string | null;
  delivery_state: string;
  tombstone: boolean;
  metadata: Record<string, unknown>;
  blocks: ConversationBlock[];
}

export interface ConversationThreadListResponse {
  user: {
    user_id: number;
    username: string;
    email: string;
    user_status: string;
  };
  items: ConversationThreadRow[];
  pagination: Pagination;
}

export interface ConversationMessageListResponse {
  thread: ConversationThreadRow;
  items: ConversationMessage[];
  pagination: Pagination;
}

export interface ConversationUserListQuery {
  page: number;
  page_size: number;
  user_id?: string;
  keyword?: string;
  started_at?: string;
  ended_at?: string;
  model_name?: string;
  is_active?: string;
  has_user_message?: string;
  min_message_count?: string;
  max_message_count?: string;
  min_thread_count?: string;
  max_thread_count?: string;
  ordering?: string;
}

export interface ConversationThreadListQuery {
  page: number;
  page_size: number;
  keyword?: string;
  thread_id?: string;
  started_at?: string;
  ended_at?: string;
  model_name?: string;
  deleted_filter?: 'all' | 'active' | 'deleted';
  has_tool?: string;
  has_attachment?: string;
  has_failed_message?: string;
}

export interface ConversationMessageListQuery {
  page: number;
  page_size: number;
  role?: string;
  include_tombstone?: string;
  include_raw?: string;
  block_kind?: string;
  before?: string;
  after?: string;
}

export function fetchConversationUsers(params: ConversationUserListQuery) {
  return http.get<unknown, ConversationUserListResponse>('/api/admin/v1/conversations/users/', { params });
}

export function fetchConversationUserSummary(userId: number, config?: RequestConfig) {
  return http.get<unknown, ConversationUserSummary>(
    `/api/admin/v1/conversations/users/${userId}/summary/`,
    config,
  );
}

export function fetchConversationThreads(userId: number, params: ConversationThreadListQuery, config?: RequestConfig) {
  return http.get<unknown, ConversationThreadListResponse>(
    `/api/admin/v1/conversations/users/${userId}/threads/`,
    { ...config, params },
  );
}

export function fetchConversationMessages(
  userId: number,
  threadId: string,
  params: ConversationMessageListQuery,
  config?: RequestConfig,
) {
  return http.get<unknown, ConversationMessageListResponse>(
    `/api/admin/v1/conversations/users/${userId}/threads/${threadId}/messages/`,
    { ...config, params },
  );
}

export function fetchConversationBlockDetail(
  userId: number,
  threadId: string,
  blockId: string,
  config?: RequestConfig,
) {
  return http.get<unknown, ConversationBlock>(
    `/api/admin/v1/conversations/users/${userId}/threads/${threadId}/blocks/${blockId}/detail/`,
    config,
  );
}

export function fetchConversationMessageDebug(
  userId: number,
  threadId: string,
  messageDbId: number,
  config?: RequestConfig,
) {
  return http.get<unknown, ConversationMessageDebug>(
    `/api/admin/v1/conversations/users/${userId}/threads/${threadId}/messages/${messageDbId}/debug/`,
    config,
  );
}
