import http from '../http';
export interface Provider { id: string; name: string; host: string; enabled: boolean }
export interface Slot { id: string; name: string; provider: string; active_version: number; enabled: boolean }
export interface Model { id: string; name: string; provider: string; model_id: string; adapter_id: string; endpoint: string; capabilities: string[]; enabled: boolean }
export interface SceneDraft { model: string; credential_slot: string; parameters: Record<string, unknown>; timeout_seconds: number }
export interface Draft { minimum_build: number; scenes: Record<string, SceneDraft> }
export interface State { draft: Draft; revision: number; channel_version: number; current: string | null; enabled: boolean; disabled_scenes: string[] }
export interface Release { id: string; sequence: number; snapshot: {minimum_build: number; scenes: Record<string, {model_id: string; adapter_id: string; endpoint: string; credential_slot_id: string; parameters: Record<string, unknown>}>}; config_hash: string; reason: string; actor_id: number; created_at: string }
export interface TestRun { id: string; state: string; results: Record<string, unknown>; created_at: string; versions: Record<string, number> }
const base = '/api/admin/v1/ai-runtime/';
export const runtime = {
  get: <T>(path: string, params?: Record<string, unknown>) => http.get<unknown, T>(base + path, {params}),
  post: <T>(path: string, data: unknown) => http.post<unknown, T>(base + path, data),
  put: <T>(path: string, data: unknown) => http.put<unknown, T>(base + path, data),
  patch: <T>(path: string, data: unknown) => http.patch<unknown, T>(base + path, data),
};
