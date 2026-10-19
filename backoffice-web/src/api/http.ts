import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type { ApiEnvelope } from '../types';

const baseURL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '');

const http = axios.create({
  baseURL,
  timeout: 15000,
});

type RequestWithRetry = InternalAxiosRequestConfig & { _retry?: boolean };

let refreshPromise: Promise<void> | null = null;

function refreshAccessToken(): Promise<void> {
  if (refreshPromise) {
    return refreshPromise;
  }
  refreshPromise = (async () => {
    const refresh = localStorage.getItem('admin_refresh_token');
    if (!refresh) {
      throw new Error('no_refresh_token');
    }
    const { data } = await axios.post<{
      access?: string;
      access_token?: string;
      refresh?: string | null;
      refresh_token?: string | null;
    }>(
      `${baseURL}/api/v1/auth/token/refresh/`,
      { refresh },
      { timeout: 15000 },
    );
    const access = data?.access ?? data?.access_token;
    if (!access) {
      throw new Error('refresh_no_access');
    }
    localStorage.setItem('admin_access_token', access);
    const rotatedRefresh = data?.refresh ?? data?.refresh_token;
    if (rotatedRefresh) {
      localStorage.setItem('admin_refresh_token', rotatedRefresh);
    }
  })().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) { super(message); this.name = 'ApiError'; this.status = status; }
}
function describeError(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(describeError).join('；');
  if (value && typeof value === 'object') return Object.entries(value).map(([key, v]) =>
    ['detail', 'non_field_errors'].includes(key) ? describeError(v) : `${key}：${describeError(v)}`).join('；');
  return '';
}
function toDisplayError(error: AxiosError): Error {
  const status = error.response?.status;
  const body = error.response?.data as Record<string, unknown> | undefined;
  return new ApiError(status === 401 ? '登录已过期，请重新登录' :
    describeError(body?.msg ?? body?.detail ?? body) || error.message || '请求失败', status);
}

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => {
    const payload = response.data as ApiEnvelope<unknown>;
    if (payload && typeof payload.code === 'number') {
      if (payload.code !== 0) {
        const m = payload.msg;
        let text = 'Request failed';
        if (typeof m === 'string') {
          text = m;
        } else if (m && typeof m === 'object' && 'detail' in m) {
          const d = (m as { detail?: string }).detail;
          if (typeof d === 'string') {
            text = d;
          }
        }
        return Promise.reject(new ApiError(describeError(m) || text, payload.code));
      }
      return payload.data;
    }
    return response.data;
  },
  async (error: AxiosError) => {
    const original = error.config as RequestWithRetry | undefined;
    const status = error.response?.status;

    if (status === 401 && original && !original._retry) {
      original._retry = true;
      try {
        await refreshAccessToken();
        const token = localStorage.getItem('admin_access_token');
        if (token) {
          original.headers.Authorization = `Bearer ${token}`;
          return http(original);
        }
        return Promise.reject(new Error('登录已过期，请重新登录'));
      } catch {
        localStorage.removeItem('admin_access_token');
        localStorage.removeItem('admin_refresh_token');
        if (typeof window !== 'undefined' && !window.location.pathname.includes('/login')) {
          window.location.assign('/login');
        }
        return Promise.reject(new Error('登录已过期，请重新登录'));
      }
    }

    return Promise.reject(error instanceof AxiosError ? toDisplayError(error) : error);
  },
);

export default http;
