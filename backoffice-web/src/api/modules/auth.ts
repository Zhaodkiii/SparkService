import http from '../http';
import type { AdminUser, MenuNode } from '../../types';

export interface LoginResponse {
  access: string;
  refresh: string;
  user: AdminUser;
}

export interface ProfileResponse {
  user: AdminUser;
  roles: string[];
  permissions: string[];
  menus: MenuNode[];
}

export function adminLogin(username: string, password: string) {
  return http.post<unknown, LoginResponse>('/api/admin/v1/auth/login/', { username, password });
}

export function fetchAdminProfile() {
  return http.get<unknown, ProfileResponse>('/api/admin/v1/auth/profile/');
}
