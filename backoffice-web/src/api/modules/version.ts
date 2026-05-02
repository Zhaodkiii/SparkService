import http from '../http';
import type { Pagination } from '../../types';

export interface AppVersionConfig {
  id: number;
  platform: string;
  bundle_id: string;
  channel: string;
  latest_version: string;
  latest_build: string;
  force_update_min_version: string;
  force_update_min_build: string;
  update_title: string;
  update_message: string;
  release_notes: string;
  download_url: string;
  enable_gradual_release: boolean;
  gradual_release_percentage: number;
  gradual_release_min_version: string;
  is_active: boolean;
  created_by_name: string;
  created_at: string;
  updated_at: string;
}

export interface VersionCheckLog {
  id: number;
  platform: string;
  bundle_id: string;
  channel: string;
  current_version: string;
  current_build: string;
  device_id: string;
  system_version: string;
  user_name: string;
  has_update: boolean;
  force_update: boolean;
  latest_version: string;
  latest_build: string;
  decision_reason: string;
  ip_address: string;
  request_id: string;
  checked_at: string;
}

export interface PageResponse<T> {
  items: T[];
  pagination: Pagination;
}

export function fetchVersionConfigs(params: Record<string, unknown>) {
  return http.get<unknown, PageResponse<AppVersionConfig>>('/api/admin/v1/version/configs/', { params });
}

export function createVersionConfig(payload: Record<string, unknown>) {
  return http.post<unknown, AppVersionConfig>('/api/admin/v1/version/configs/', payload);
}

export function updateVersionConfig(id: number, payload: Record<string, unknown>) {
  return http.patch<unknown, AppVersionConfig>(`/api/admin/v1/version/configs/${id}/`, payload);
}

export function disableVersionConfig(id: number) {
  return http.delete(`/api/admin/v1/version/configs/${id}/`);
}

export function fetchVersionCheckLogs(params: Record<string, unknown>) {
  return http.get<unknown, PageResponse<VersionCheckLog>>('/api/admin/v1/version/logs/', { params });
}
