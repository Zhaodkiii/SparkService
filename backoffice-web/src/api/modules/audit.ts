import http from '../http';
import type { Pagination } from '../../types';

export interface AuditLogItem {
  id: number;
  user_name: string;
  action: string;
  resource_type: string;
  resource_id: string;
  method: string;
  path: string;
  status_code: number;
  request_id: string;
  created_at: string;
}

export interface AuditLogList {
  items: AuditLogItem[];
  pagination: Pagination;
}

export interface SystemLogModule {
  value: string;
  label: string;
  file: string;
  available_dates?: string[];
}

export interface SystemLogModulesResponse {
  log_root: string;
  date_pattern: string;
  host_path_hint: string;
  items: SystemLogModule[];
}

export interface SystemLogQueryContext {
  log_root: string;
  date_pattern: string;
  host_path_hint: string;
  date?: string;
  file?: string;
  log_file?: string;
  host_log_file?: string;
  file_exists?: boolean;
}

export interface SystemLogItem {
  id: string;
  date: string;
  module: string;
  file: string;
  line_no: number;
  timestamp: string | null;
  level: string;
  logger: string;
  request_id: string;
  method?: string;
  path?: string;
  status_code?: number;
  duration_ms?: number;
  error_code?: number;
  error_message?: string;
  message: string;
  raw_preview: string;
}

export interface SystemLogDetail {
  date: string;
  module: string;
  file: string;
  line_no: number;
  parsed: Record<string, unknown>;
  raw: string | Record<string, unknown>;
  related_query: { request_id?: string };
}

export function fetchAuditLogs(params: {
  page: number;
  page_size: number;
  action?: string;
  status_code?: string;
  request_id?: string;
  path?: string;
  resource_type?: string;
  date_from?: string;
  date_to?: string;
}) {
  return http.get<unknown, AuditLogList>('/api/admin/v1/audit/logs/', { params });
}

export function fetchSystemLogModules() {
  return http.get<unknown, SystemLogModulesResponse>('/api/admin/v1/audit/system-log-modules/');
}

export function fetchSystemLogs(params: Record<string, unknown>) {
  return http.get<
    unknown,
    { items: SystemLogItem[]; pagination: Pagination; scan_limited?: boolean; context?: SystemLogQueryContext }
  >(
    '/api/admin/v1/audit/system-logs/',
    { params },
  );
}

export function fetchSystemLogDetail(params: { date: string; module: string; line_no: number }) {
  return http.get<unknown, SystemLogDetail>('/api/admin/v1/audit/system-logs/detail/', { params });
}
