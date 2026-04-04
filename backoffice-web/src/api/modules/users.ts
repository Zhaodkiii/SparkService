import http from '../http';
import type { AdminUser, Pagination } from '../../types';

export interface UserListResponse {
  items: AdminUser[];
  pagination: Pagination;
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
