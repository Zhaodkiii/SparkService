import http from '../http';
import type { Pagination } from '../../types';

export interface QuickQuestionConfig {
  id: number;
  title: string;
  prompt: string;
  prompt_preview: string;
  category: string;
  locale: string;
  is_active: boolean;
  metadata: Record<string, unknown>;
  created_by: number | null;
  created_by_name: string;
  updated_by: number | null;
  updated_by_name: string;
  created_at: string;
  updated_at: string;
}

export interface QuickQuestionConfigListResponse {
  items: QuickQuestionConfig[];
  pagination: Pagination;
}

export interface QuickQuestionConfigListQuery {
  page: number;
  page_size: number;
  keyword?: string;
  category?: string;
  locale?: string;
  is_active?: string;
}

export interface QuickQuestionConfigPayload {
  title: string;
  prompt: string;
  category: string;
  locale: string;
  is_active: boolean;
  metadata?: Record<string, unknown>;
}

export interface QuickQuestionConfigPatchPayload {
  title?: string;
  prompt?: string;
  category?: string;
  locale?: string;
  metadata?: Record<string, unknown>;
}

export interface GeneratedQuestionRecord {
  id: number;
  title: string;
  prompt: string;
  prompt_preview: string;
  category: string;
  user: number;
  user_name: string;
  member: number;
  member_name: string;
  click_count: number;
  created_at: string;
  updated_at: string;
}

export interface GeneratedQuestionRecordListResponse {
  items: GeneratedQuestionRecord[];
  pagination: Pagination;
}

export interface GeneratedQuestionRecordListQuery {
  page: number;
  page_size: number;
  keyword?: string;
  user_id?: string;
  member_id?: string;
  category?: string;
  created_at_start?: string;
  created_at_end?: string;
  click_count_min?: string;
  click_count_max?: string;
}

export function fetchQuickQuestionConfigs(params: QuickQuestionConfigListQuery) {
  return http.get<unknown, QuickQuestionConfigListResponse>(
    '/api/admin/v1/conversations/quick-questions/configs/',
    { params },
  );
}

export function fetchQuickQuestionConfig(id: number) {
  return http.get<unknown, QuickQuestionConfig>(
    `/api/admin/v1/conversations/quick-questions/configs/${id}/`,
  );
}

export function createQuickQuestionConfig(payload: QuickQuestionConfigPayload) {
  return http.post<unknown, QuickQuestionConfig>(
    '/api/admin/v1/conversations/quick-questions/configs/',
    payload,
  );
}

export function updateQuickQuestionConfig(id: number, payload: QuickQuestionConfigPatchPayload) {
  return http.patch<unknown, QuickQuestionConfig>(
    `/api/admin/v1/conversations/quick-questions/configs/${id}/`,
    payload,
  );
}

export function enableQuickQuestionConfig(id: number) {
  return http.post<unknown, QuickQuestionConfig>(
    `/api/admin/v1/conversations/quick-questions/configs/${id}/enable/`,
  );
}

export function disableQuickQuestionConfig(id: number) {
  return http.post<unknown, QuickQuestionConfig>(
    `/api/admin/v1/conversations/quick-questions/configs/${id}/disable/`,
  );
}

export function fetchGeneratedQuestionRecords(params: GeneratedQuestionRecordListQuery) {
  return http.get<unknown, GeneratedQuestionRecordListResponse>(
    '/api/admin/v1/conversations/quick-questions/generated-records/',
    { params },
  );
}

export function fetchGeneratedQuestionRecord(id: number) {
  return http.get<unknown, GeneratedQuestionRecord>(
    `/api/admin/v1/conversations/quick-questions/generated-records/${id}/`,
  );
}