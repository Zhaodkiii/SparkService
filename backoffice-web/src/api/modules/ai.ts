import http from '../http';

/** GET /ai/scenarios/ — seven fixed rows, aggregate per scenario */
export interface AIScenarioSummary {
  scenario: string;
  label: string;
  models_count: number;
  default_model: string | null;
  active_bindings: number;
}

/** GET/PATCH scenario binding (multi-model row) */
export interface AIScenarioModelBinding {
  id: number;
  scenario: string;
  identity: string;
  model: string;
  endpoint: string;
  provider_company?: string;
  provider_name?: string;
  temperature: number;
  max_tokens: number;
  position: number;
  is_default: boolean;
  is_active: boolean;
}

export function fetchAIScenarioSummaries() {
  return http.get<unknown, AIScenarioSummary[]>('/api/admin/v1/ai/scenarios/');
}

export function fetchScenarioBindings(scenarioKey: string) {
  return http.get<unknown, AIScenarioModelBinding[]>(`/api/admin/v1/ai/scenarios/${scenarioKey}/models/`);
}

export function createScenarioBinding(scenarioKey: string, payload: Record<string, unknown>) {
  return http.post(`/api/admin/v1/ai/scenarios/${scenarioKey}/models/`, payload);
}

export function updateScenarioBinding(bindingId: number, payload: Record<string, unknown>) {
  return http.patch(`/api/admin/v1/ai/scenario-models/${bindingId}/`, payload);
}

export function deleteScenarioBinding(bindingId: number) {
  return http.delete(`/api/admin/v1/ai/scenario-models/${bindingId}/`);
}

export interface AIProvider {
  id: number;
  kind: string;
  name: string;
  company: string;
  request_url: string;
  is_hidden: boolean;
  is_using: boolean;
  capability_class: string;
  help: string;
  privacy_policy_url: string;
  source: string;
  position: number;
  is_active: boolean;
}

export interface AIModelCatalog {
  id: number;
  name: string;
  display_name: string;
  position: number;
  company: string;
  is_hidden: boolean;
  supports_search: boolean;
  supports_multimodal: boolean;
  supports_reasoning: boolean;
  supports_tool_use: boolean;
  supports_voice_gen: boolean;
  supports_image_gen: boolean;
  /** 0 免费 1 经济 2 标准 3 高级 */
  price_tier: number;
  supports_text: boolean;
  reasoning_controllable: boolean;
  source: string;
  is_active: boolean;
}

export function fetchAIModelCatalog() {
  return http.get<unknown, AIModelCatalog[]>('/api/admin/v1/ai/models/');
}

export function createAIModelCatalog(payload: Record<string, unknown>) {
  return http.post('/api/admin/v1/ai/models/', payload);
}

export function updateAIModelCatalog(id: number, payload: Record<string, unknown>) {
  return http.patch(`/api/admin/v1/ai/models/${id}/`, payload);
}

export function fetchAIProviders(kind = '') {
  return http.get<unknown, AIProvider[]>('/api/admin/v1/ai/providers/', { params: { kind } });
}

export function createAIProvider(payload: Record<string, unknown>) {
  return http.post('/api/admin/v1/ai/providers/', payload);
}

export function updateAIProvider(id: number, payload: Record<string, unknown>) {
  return http.patch(`/api/admin/v1/ai/providers/${id}/`, payload);
}

export interface TrialApplicationItem {
  id: number;
  user: number;
  applicant: string;
  applicant_email: string;
  status: string;
  grant_source: string;
  started_at: string | null;
  expires_at: string | null;
  created_at: string;
}

export interface TrialListResponse {
  items: TrialApplicationItem[];
  pagination: { page: number; page_size: number; total: number; total_pages: number };
}

export function fetchAITrials(params: { page: number; page_size: number; status?: string }) {
  return http.get<unknown, TrialListResponse>('/api/admin/v1/ai/trials/', { params });
}

export function trialAction(trialId: number, action: 'approve' | 'reject' | 'recycle', note = '') {
  return http.post(`/api/admin/v1/ai/trials/${trialId}/${action}/`, { note });
}
