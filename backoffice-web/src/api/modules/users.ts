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

export interface AdminUserTrustedDevice {
  id: number;
  bundle_id: string;
  device_id: string;
  app_version: string;
  build_version: string;
  bundle_identifier: string;
  push_token_masked: string;
  notifications_enabled: boolean;
  platform: string;
  system_version: string;
  device_model: string;
  device_model_name: string;
  device_name: string;
  country_code: string;
  region_code: string;
  language_code: string;
  is_simulator: boolean;
  is_revoked: boolean;
  first_seen: string;
  last_seen: string;
  request_id: string;
}

export interface AdminUserDeviceSession {
  id: number;
  trusted_device: number;
  bundle_id: string;
  device_id: string;
  session_version: number;
  status: string;
  revoked_reason: string;
  replaced_by: number | null;
  last_refreshed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminUserProSummary {
  is_pro: boolean;
  status: string;
  grant_source: string;
  started_at: string | null;
  expires_at: string | null;
  remaining_seconds: number;
  trial_id: number | null;
  latest_request_id: number | null;
}

export interface AdminUserAuthIdentity {
  id: number;
  provider: string;
  provider_label: string;
  provider_uid_masked: string;
  provider_uid_plain: string | null;
  bundle_id: string;
  created_at: string;
  updated_at: string;
}

export interface AdminIdentityScopeOption {
  value: string;
  label: string;
}

export interface AdminIdentityMutationResponse {
  user_id: number;
  auth_identities: AdminUserAuthIdentity[];
  remaining_count: number;
}

export interface AdminUserDetail {
  user: AdminUser;
  pro: AdminUserProSummary;
  auth_identities: AdminUserAuthIdentity[];
  trusted_devices: AdminUserTrustedDevice[];
  device_sessions: AdminUserDeviceSession[];
}

export function fetchUsers(params: {
  page: number;
  page_size: number;
  q?: string;
  is_active?: string;
  bundle_id?: string;
  date_joined_after?: string;
  date_joined_before?: string;
  last_used_after?: string;
  last_used_before?: string;
  sort_by?: string;
  order?: 'asc' | 'desc';
}) {
  return http.get<unknown, UserListResponse>('/api/admin/v1/users/', { params });
}

export function updateUserStatus(userId: number, isActive: boolean) {
  return http.post(`/api/admin/v1/users/${userId}/status/`, { is_active: isActive });
}

export function fetchUserDetail(userId: number) {
  return http.get<unknown, AdminUserDetail>(`/api/admin/v1/users/${userId}/detail/`);
}

export function fetchIdentityScopeOptions() {
  return http.get<unknown, { options: AdminIdentityScopeOption[] }>('/api/admin/v1/users/identity-scopes/');
}

export function createUserAuthIdentity(
  userId: number,
  payload: { provider: 'phone' | 'email'; provider_uid: string; bundle_id: string },
) {
  return http.post<unknown, AdminIdentityMutationResponse>(
    `/api/admin/v1/users/${userId}/auth-identities/`,
    payload,
  );
}

export function updateUserAuthIdentity(
  userId: number,
  identityId: number,
  payload: { provider_uid: string },
) {
  return http.patch<unknown, AdminIdentityMutationResponse>(
    `/api/admin/v1/users/${userId}/auth-identities/${identityId}/`,
    payload,
  );
}

export function deleteUserAuthIdentity(userId: number, identityId: number) {
  return http.delete<unknown, AdminIdentityMutationResponse>(
    `/api/admin/v1/users/${userId}/auth-identities/${identityId}/`,
  );
}

export function grantUserPro(
  userId: number,
  payload: { grant_days?: number; expires_at?: string | null; note?: string },
) {
  return http.post<unknown, { user_id: number; pro: AdminUserProSummary }>(
    `/api/admin/v1/users/${userId}/pro/grant/`,
    payload,
  );
}

export function recycleUserPro(userId: number, payload: { note?: string } = {}) {
  return http.post<unknown, { user_id: number; pro: AdminUserProSummary }>(
    `/api/admin/v1/users/${userId}/pro/recycle/`,
    payload,
  );
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

export interface AdminAccessDenyEntry {
  id: number;
  dimension: 'user_id' | 'phone' | 'email' | 'device';
  dimension_value: string;
  display_value: string;
  reason_code: string;
  reason_note: string;
  source: string;
  related_user_id: number | null;
  related_user_display: string;
  expires_at: string | null;
  revoked_at: string | null;
  is_active: boolean;
  sms_status: string;
  created_by_id: number | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface AccessDenyListResponse {
  items: AdminAccessDenyEntry[];
  pagination: Pagination;
}

export interface AccessDenyCreatePayload {
  user_id?: number;
  phone?: string;
  email?: string;
  device_id?: string;
  reason_note?: string;
}

export function fetchAccessDenyList(params: {
  page: number;
  page_size: number;
  q?: string;
  dimension?: string;
  active_only?: string;
}) {
  return http.get<unknown, AccessDenyListResponse>('/api/admin/v1/users/blacklist/', { params });
}

export function createAccessDenyEntry(payload: AccessDenyCreatePayload) {
  return http.post<unknown, { result: Record<string, unknown>; entry: AdminAccessDenyEntry | null }>(
    '/api/admin/v1/users/blacklist/',
    payload,
  );
}

export function revokeAccessDenyEntry(entryId: number) {
  return http.post<unknown, AdminAccessDenyEntry>(`/api/admin/v1/users/blacklist/${entryId}/revoke/`, {});
}

export interface AdminAccessDenyHit {
  id: number;
  deny_entry_id: number | null;
  action: 'login' | 'register' | 'otp_request' | 'identity_bind';
  hit_dimension: 'user_id' | 'phone' | 'email' | 'device';
  hit_value: string;
  reason_code: string;
  provider: string;
  attempted_user_id: number | null;
  attempted_email: string;
  attempted_phone: string;
  attempted_identity: string;
  device_id: string;
  bundle_id: string;
  ip_address: string;
  user_agent: string;
  request_id: string;
  created_at: string;
}

export interface AccessDenyHitListResponse {
  items: AdminAccessDenyHit[];
  pagination: Pagination;
}

export function fetchAccessDenyHits(params: {
  page: number;
  page_size: number;
  q?: string;
  action?: string;
  hit_dimension?: string;
  provider?: string;
  deny_entry_id?: string;
  date_from?: string;
  date_to?: string;
}) {
  return http.get<unknown, AccessDenyHitListResponse>('/api/admin/v1/users/blacklist/hits/', { params });
}
