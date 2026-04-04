import http from '../http';

export interface RoleItem {
  id: number;
  name: string;
  code: string;
  description: string;
  is_active: boolean;
}

export interface PermissionItem {
  id: number;
  name: string;
  code: string;
  permission_type: 'menu' | 'button' | 'api';
  path: string;
  method: string;
  parent_code: string;
  is_active: boolean;
}

export function fetchRoles() {
  return http.get<unknown, RoleItem[]>('/api/admin/v1/rbac/roles/');
}

export function createRole(payload: Partial<RoleItem>) {
  return http.post('/api/admin/v1/rbac/roles/', payload);
}

export function fetchPermissions() {
  return http.get<unknown, PermissionItem[]>('/api/admin/v1/rbac/permissions/');
}

export function assignRolePermissions(roleId: number, permissionCodes: string[]) {
  return http.post(`/api/admin/v1/rbac/roles/${roleId}/permissions/`, { permission_codes: permissionCodes });
}

export function fetchRolePermissions(roleId: number) {
  return http.get<unknown, { role_id: number; permission_codes: string[] }>(`/api/admin/v1/rbac/roles/${roleId}/permissions/`);
}
