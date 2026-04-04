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

export function fetchAuditLogs(params: { page: number; page_size: number; action?: string; status_code?: string }) {
  return http.get<unknown, AuditLogList>('/api/admin/v1/audit/logs/', { params });
}
