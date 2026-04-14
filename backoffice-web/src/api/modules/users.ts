import http from '../http';
import type { AdminUser, Pagination } from '../../types';

export interface UserListResponse {
  items: AdminUser[];
  pagination: Pagination;
}

export interface AdminDevice {
  id: number;
  user: number | null;
  user_name: string;
  user_email: string;
  bundle_id: string;
  device_id: string;
  platform: string;
  system_version: string;
  device_model: string;
  device_name: string;
  verified: boolean;
  notifications_enabled: boolean;
  is_revoked: boolean;
  first_seen: string;
  last_seen: string;
}

export interface DeviceListResponse {
  items: AdminDevice[];
  pagination: Pagination;
}

export interface AdminDeactivation {
  id: number;
  user: number;
  user_name: string;
  user_email: string;
  state: string;
  requested_at: string;
  scheduled_at: string | null;
  processed_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  failed_at: string | null;
  freeze_email: string;
  freeze_phone_number: string;
  error_message: string;
  request_id: string;
  created_at: string;
}

export interface DeactivationListResponse {
  items: AdminDeactivation[];
  pagination: Pagination;
}

export interface AdminDeactivationAudit {
  id: number;
  deactivation: number;
  action: string;
  request_id: string;
  details: Record<string, unknown> | null;
  created_at: string;
}

export function fetchUsers(params: { page: number; page_size: number; q?: string; is_active?: string }) {
  return http.get<unknown, UserListResponse>('/api/admin/v1/users/', { params });
}

export function updateUserStatus(userId: number, isActive: boolean) {
  return http.post(`/api/admin/v1/users/${userId}/status/`, { is_active: isActive });
}

export function assignUserRoles(userId: number, roleCodes: string[]) {
  return http.post(`/api/admin/v1/users/${userId}/roles/`, { role_codes: roleCodes });
}

export function fetchDevices(params: {
  page: number;
  page_size: number;
  q?: string;
  user_id?: string;
  is_revoked?: string;
}) {
  return http.get<unknown, DeviceListResponse>('/api/admin/v1/users/devices/', { params });
}

export function updateDeviceRevoked(deviceId: number, isRevoked: boolean) {
  return http.post(`/api/admin/v1/users/devices/${deviceId}/revoke/`, { is_revoked: isRevoked });
}

export function fetchDeactivations(params: { page: number; page_size: number; q?: string; state?: string }) {
  return http.get<unknown, DeactivationListResponse>('/api/admin/v1/users/deactivations/', { params });
}

export function fetchDeactivationAudits(deactivationId: number) {
  return http.get<unknown, AdminDeactivationAudit[]>(`/api/admin/v1/users/deactivations/${deactivationId}/audits/`);
}

export function cancelDeactivation(deactivationId: number) {
  return http.post(`/api/admin/v1/users/deactivations/${deactivationId}/cancel/`, {});
}

export function retryDeactivation(deactivationId: number) {
  return http.post(`/api/admin/v1/users/deactivations/${deactivationId}/retry/`, {});
}
