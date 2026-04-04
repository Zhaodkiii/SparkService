import { defineStore } from 'pinia';
import type { AdminUser, MenuNode } from '../types';
import { adminLogin, fetchAdminProfile } from '../api/modules/auth';

interface AuthState {
  user: AdminUser | null;
  roles: string[];
  permissions: string[];
  menus: MenuNode[];
  accessToken: string;
  refreshToken: string;
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    roles: [],
    permissions: [],
    menus: [],
    accessToken: localStorage.getItem('admin_access_token') || '',
    refreshToken: localStorage.getItem('admin_refresh_token') || '',
  }),
  getters: {
    isAuthenticated: (state) => !!state.accessToken,
  },
  actions: {
    async login(username: string, password: string) {
      const data = await adminLogin(username, password);
      this.accessToken = data.access;
      this.refreshToken = data.refresh;
      this.user = data.user;
      localStorage.setItem('admin_access_token', data.access);
      localStorage.setItem('admin_refresh_token', data.refresh);
      await this.loadProfile();
    },
    async loadProfile() {
      const data = await fetchAdminProfile();
      this.user = data.user;
      this.roles = data.roles;
      this.permissions = data.permissions;
      this.menus = data.menus;
    },
    hasPermission(code: string) {
      if (this.user?.is_superuser) {
        return true;
      }
      return this.permissions.includes(code);
    },
    logout() {
      this.user = null;
      this.roles = [];
      this.permissions = [];
      this.menus = [];
      this.accessToken = '';
      this.refreshToken = '';
      localStorage.removeItem('admin_access_token');
      localStorage.removeItem('admin_refresh_token');
    },
  },
});
