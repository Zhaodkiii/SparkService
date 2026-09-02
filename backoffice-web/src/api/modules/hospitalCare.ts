import http from '../http';
import type { Pagination } from '../../types';

export type HospitalStatus = 'draft' | 'active' | 'suspended';
export type HospitalServiceMode = 'demo' | 'redirect' | 'integrated';
export type DepartmentStatus = 'active' | 'hidden';
export type StaffRole = 'hospital_admin' | 'doctor' | 'nurse' | 'auditor';
export type StaffStatus = 'invited' | 'active' | 'suspended';
export type LicenseStatus = 'unverified' | 'verified' | 'suspended';
export type DoctorProfileStatus = 'draft' | 'active' | 'hidden';
export type AgentPublicationStatus = 'draft' | 'review' | 'published' | 'disabled';
export type KnowledgeVectorStatus = 'not_built' | 'current' | 'stale';

export interface HospitalOverview {
  department_count: number;
  doctor_count: number;
  published_agent_count: number;
  active_conversation_count: number;
  pending_license_count: number;
  pending_review_agent_count: number;
}

export interface HospitalRow {
  id: string;
  code: string;
  name: string;
  short_name: string;
  grade: string;
  address: string;
  service_phone: string;
  emergency_phone: string;
  website_url: string;
  introduction: string;
  service_mode: HospitalServiceMode;
  status: HospitalStatus;
  province_code: string;
  city_code: string;
  district_code: string;
  registration_redirect_url: string;
  logo_file_id: number | null;
  version: number;
  created_at: string;
  updated_at: string;
  department_count?: number | null;
  doctor_count?: number | null;
  overview?: HospitalOverview;
}

export interface HospitalCounts {
  total: number;
  active: number;
  draft: number;
  suspended: number;
}

export interface HospitalListResponse {
  items: HospitalRow[];
  pagination: Pagination;
  counts: HospitalCounts;
}

export interface HospitalDraft {
  code: string;
  name: string;
  short_name: string;
  grade: string;
  province_code: string;
  city_code: string;
  district_code: string;
  address: string;
  service_phone: string;
  emergency_phone: string;
  website_url: string;
  introduction: string;
  registration_redirect_url: string;
  service_mode: HospitalServiceMode;
}

export interface DepartmentRow {
  id: string;
  hospital_id: string;
  parent_id: string | null;
  code: string;
  name: string;
  short_name: string;
  description: string;
  sort_order: number;
  status: DepartmentStatus;
  doctor_count?: number | null;
  agent_count?: number | null;
}

export interface StaffRow {
  id: string;
  user_id: number;
  username: string;
  role: StaffRole;
  employee_no: string;
  status: StaffStatus;
  display_name: string;
  license_status: string;
}

export interface DoctorRow {
  id: string;
  display_name: string;
  title: string;
  specialties: string[];
  introduction: string;
  license_status: LicenseStatus;
  profile_status: DoctorProfileStatus;
}

export interface AgentRow {
  id: string;
  hospital_id: string;
  department: DepartmentRow | null;
  doctor: DoctorRow;
  name: string;
  public_summary: string;
  greeting: string;
  service_boundary: string;
  publication_status: AgentPublicationStatus;
  published_at: string | null;
  scenario_binding_id?: number | null;
  version?: number;
  created_at?: string | null;
  updated_at?: string | null;
  binding?: AgentBinding | null;
  knowledge_bindings?: AgentKnowledgeBinding[];
}

export interface AgentBinding {
  id: number;
  model: string;
  model_display_name: string;
  display_name: string;
  temperature: number;
  max_tokens: number;
  system_provision: string;
  brief_description: string;
  ai_tool_scenarios: string[];
  server_tool_scenarios: string[];
  related_task_codes: string[];
  is_default: boolean;
  is_active: boolean;
  updated_at: string | null;
}

export interface AgentKnowledgeBinding {
  knowledge_base_id: string;
  profile_id: string | null;
  name: string;
  usage_scope: string;
  status: string;
  sort_order: number;
}

export interface AgentFormOptions {
  doctors: DoctorRow[];
  departments: DepartmentRow[];
  models: Array<{ name: string; display_name: string; company: string }>;
  knowledge_bases: Array<{ id: string; name: string; vector_status: KnowledgeVectorStatus }>;
  embedding_bindings: EmbeddingBindingOption[];
  ai_tool_scenarios: Array<{ value: string; label: string }>;
  server_tool_scenarios: Array<{ value: string; label: string }>;
}

export interface EmbeddingBindingOption {
  id: number;
  display_name: string;
  model: string;
  is_default: boolean;
  is_active: boolean;
}

export interface KnowledgeBaseRow {
  id: string;
  hospital_id: string;
  knowledge_base_id: string;
  name: string;
  description: string;
  vector_status: KnowledgeVectorStatus;
  indexed_revision: number | null;
  revision: number | null;
  embedding_binding_id: number | null;
  department_ids: string[];
  departments?: DepartmentRow[];
  document_count?: number | null;
  agent_count?: number | null;
  version: number;
  created_at: string;
  updated_at: string;
  documents?: KnowledgeDocumentRow[];
  embedding_bindings?: EmbeddingBindingOption[];
  is_deleted?: boolean;
}

export interface KnowledgeDocumentRow {
  id: string;
  title: string;
  content: string;
  excerpt: string;
  revision: number;
  updated_at: string | null;
  created_at: string | null;
}

export interface AgentCreatePayload {
  doctor_id: string;
  department_id: string;
  name: string;
  public_summary?: string;
  greeting?: string;
  service_boundary?: string;
  binding: {
    model: string;
    display_name?: string;
    temperature?: number;
    max_tokens?: number;
    system_provision?: string;
    brief_description?: string;
    ai_tool_scenarios?: string[];
    server_tool_scenarios?: string[];
    related_task_codes?: string[];
  };
  knowledge_bases?: Array<{ profile_id: string }>;
}

export interface AgentUpdatePayload {
  version: number;
  department_id?: string;
  name?: string;
  public_summary?: string;
  greeting?: string;
  service_boundary?: string;
  binding?: AgentCreatePayload['binding'] & { updated_at?: string };
  knowledge_bases?: Array<{ profile_id: string }>;
}

export interface HospitalAuditRow {
  id: number;
  action: string;
  user_id: number | null;
  resource_type: string;
  resource_id: string;
  status_code: number;
  request_id: string;
  created_at: string;
}

const ERROR_LABELS: Record<string, string> = {
  HOSPITAL_NOT_FOUND: '医院不存在',
  HOSPITAL_CODE_CONFLICT: '医院编码已存在',
  HOSPITAL_VERSION_CONFLICT: '资料已被其他管理员更新，请刷新后重试',
  HOSPITAL_ACTIVATE_INVALID: '启用校验未通过',
  DEPARTMENT_NOT_FOUND: '科室不存在',
  DEPARTMENT_PARENT_INVALID: '上级科室无效',
  STAFF_ALREADY_EXISTS: '该用户已是本院职工',
  STAFF_NOT_FOUND: '职工不存在',
  STAFF_LAST_ADMIN: '启用中的医院至少保留一位有效医院管理员',
  STAFF_ROLE_LOCKED: '医生角色已绑定医生资料，不能在职工页改成其他角色',
  DOCTOR_PROFILE_NOT_ACTIVE: '医生资料不可用',
  AGENT_NOT_FOUND: '智能体不存在',
  AGENT_VERSION_CONFLICT: '智能体已被其他管理员更新，请刷新后重试',
  AGENT_REVIEW_INVALID: '当前状态不允许该审核动作',
  AGENT_DOCTOR_INVALID: '医生不可用或已停用',
  AGENT_DEPARTMENT_INVALID: '科室不可用或已停用',
  AGENT_BASE_MODEL_UNAVAILABLE: '基座模型或 Provider 不可用',
  HOSPITAL_KNOWLEDGE_NOT_FOUND: '知识库不存在',
  HOSPITAL_KNOWLEDGE_VERSION_CONFLICT: '知识库已被其他管理员更新，请刷新后重试',
  HOSPITAL_KNOWLEDGE_EMBEDDING_UNAVAILABLE: 'Embedding 模型或 Provider 不可用',
  HOSPITAL_KNOWLEDGE_DOCUMENT_NOT_FOUND: '文本资料不存在',
  IDEMPOTENCY_KEY_REQUIRED: '请勿重复提交',
  IDEMPOTENCY_CONFLICT: '相同请求正在处理，请稍后重试',
  REGISTRATION_REDIRECT_INVALID: '跳转地址必须是合法 HTTPS 地址',
  PAYLOAD_INVALID: '请检查必填项',
};

export function hospitalCareMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error || '请求失败');
  if (/network error/i.test(raw)) {
    return '无法连接医院管理接口。请确认后台已启动，且浏览器未拦截跨域请求。';
  }
  const [code, rest] = raw.split('：', 2);
  const label = ERROR_LABELS[code] || (code.startsWith('HOSPITAL_') || code.startsWith('AGENT_') || code.startsWith('STAFF_') ? code : raw);
  if (ERROR_LABELS[code] && rest) {
    return `${label}：${rest}`;
  }
  return ERROR_LABELS[code] || raw;
}

export function newIdempotencyKey() {
  return crypto.randomUUID();
}

function withIdempotency() {
  return { headers: { 'Idempotency-Key': newIdempotencyKey() } };
}

const HOSPITAL_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function requireHospitalId(hospitalId: string | undefined | null): string {
  const value = String(hospitalId || '').trim();
  if (!value || !HOSPITAL_ID_RE.test(value)) {
    throw new Error('缺少医院 ID');
  }
  return value;
}

function hospitalUrl(hospitalId: string, suffix = '') {
  return `/api/admin/v1/hospital-care/hospitals/${requireHospitalId(hospitalId)}${suffix}`;
}

export function fetchHospitals(params: {
  page: number;
  page_size: number;
  q?: string;
  status?: string;
  service_mode?: string;
}) {
  return http.get<unknown, HospitalListResponse>('/api/admin/v1/hospital-care/hospitals/', { params });
}

export function fetchHospital(hospitalId: string) {
  return http.get<unknown, HospitalRow>(hospitalUrl(hospitalId, '/'));
}

export function createHospital(payload: HospitalDraft) {
  return http.post<unknown, HospitalRow>('/api/admin/v1/hospital-care/hospitals/', payload, withIdempotency());
}

export function updateHospital(hospitalId: string, payload: Partial<HospitalDraft> & { version: number }) {
  return http.patch<unknown, HospitalRow>(hospitalUrl(hospitalId, '/'), payload);
}

export function activateHospital(hospitalId: string, version: number) {
  return http.post<unknown, HospitalRow>(hospitalUrl(hospitalId, '/activate/'), { version }, withIdempotency());
}

export function suspendHospital(hospitalId: string, version: number, reason: string) {
  return http.post<unknown, HospitalRow>(hospitalUrl(hospitalId, '/suspend/'), { version, reason }, withIdempotency());
}

export function fetchDepartments(hospitalId: string, params: { q?: string; status?: string } = {}) {
  return http.get<unknown, { items: DepartmentRow[] }>(hospitalUrl(hospitalId, '/departments/'), { params });
}

export function createDepartment(hospitalId: string, payload: Partial<DepartmentRow> & { code: string; name: string }) {
  return http.post<unknown, DepartmentRow>(hospitalUrl(hospitalId, '/departments/'), payload);
}

export function updateDepartment(departmentId: string, payload: Partial<DepartmentRow>) {
  return http.patch<unknown, DepartmentRow>(`/api/admin/v1/hospital-care/departments/${departmentId}/`, payload);
}

export function fetchStaff(hospitalId: string, params: { page: number; page_size: number; q?: string }) {
  return http.get<unknown, { items: StaffRow[]; pagination: Pagination }>(hospitalUrl(hospitalId, '/staff/'), { params });
}

export function updateStaff(
  staffId: string,
  payload: {
    role?: StaffRole;
    employee_no?: string;
    status?: StaffStatus;
    display_name?: string;
    title?: string;
  },
) {
  return http.patch<unknown, StaffRow>(`/api/admin/v1/hospital-care/staff/${staffId}/`, payload);
}

export function inviteStaff(
  hospitalId: string,
  payload: {
    user_id: number;
    role: StaffRole;
    employee_no?: string;
    status?: StaffStatus;
    display_name?: string;
    title?: string;
    specialties?: string[];
    introduction?: string;
  },
) {
  return http.post<unknown, { id: string; user_id: number; role: StaffRole; status: StaffStatus; employee_no: string }>(
    hospitalUrl(hospitalId, '/staff/'),
    payload,
  );
}

export function fetchDoctors(hospitalId: string, params: { page: number; page_size: number; q?: string }) {
  return http.get<unknown, { items: DoctorRow[]; pagination: Pagination }>(hospitalUrl(hospitalId, '/doctors/'), { params });
}

export function updateDoctor(
  doctorId: string,
  payload: Partial<DoctorRow> & { avatar_file_id?: number | null; primary_department_id?: string },
) {
  return http.patch<unknown, DoctorRow>(`/api/admin/v1/hospital-care/doctors/${doctorId}/`, payload);
}

export function fetchAgents(
  hospitalId: string,
  params: { page: number; page_size: number; q?: string; status?: string; department_id?: string },
) {
  return http.get<unknown, { items: AgentRow[]; pagination: Pagination }>(hospitalUrl(hospitalId, '/agents/'), { params });
}

export function reviewAgent(agentId: string, payload: { action: 'publish' | 'reject' | 'disable'; version: number; reason?: string }) {
  return http.post<unknown, AgentRow>(`/api/admin/v1/hospital-care/agents/${agentId}/review/`, payload, withIdempotency());
}

export function fetchAgentFormOptions(hospitalId: string) {
  return http.get<unknown, AgentFormOptions>(hospitalUrl(hospitalId, '/agent-form-options/'));
}

export function fetchAgent(agentId: string) {
  return http.get<unknown, AgentRow>(`/api/admin/v1/hospital-care/agents/${agentId}/`);
}

export function createAgent(hospitalId: string, payload: AgentCreatePayload) {
  return http.post<unknown, AgentRow>(hospitalUrl(hospitalId, '/agents/'), payload, withIdempotency());
}

export function updateAgent(agentId: string, payload: AgentUpdatePayload) {
  return http.patch<unknown, AgentRow>(`/api/admin/v1/hospital-care/agents/${agentId}/`, payload, withIdempotency());
}

export function fetchKnowledgeBases(
  hospitalId: string,
  params: { page?: number; page_size?: number; q?: string; department_id?: string } = {},
) {
  return http.get<unknown, { items: KnowledgeBaseRow[]; pagination: Pagination; embedding_bindings: EmbeddingBindingOption[] }>(
    hospitalUrl(hospitalId, '/knowledge-bases/'),
    { params },
  );
}

export function createKnowledgeBase(
  hospitalId: string,
  payload: { name: string; description?: string; department_ids?: string[] },
) {
  return http.post<unknown, KnowledgeBaseRow>(hospitalUrl(hospitalId, '/knowledge-bases/'), payload, withIdempotency());
}

export function fetchKnowledgeBase(profileId: string) {
  return http.get<unknown, KnowledgeBaseRow>(`/api/admin/v1/hospital-care/knowledge-bases/${profileId}/`);
}

export function updateKnowledgeBase(
  profileId: string,
  payload: { version: number; name?: string; description?: string; department_ids?: string[] },
) {
  return http.patch<unknown, KnowledgeBaseRow>(
    `/api/admin/v1/hospital-care/knowledge-bases/${profileId}/`,
    payload,
    withIdempotency(),
  );
}

export function deleteKnowledgeBase(profileId: string, version: number) {
  return http.delete<unknown, { id: string; is_deleted: boolean; version: number }>(
    `/api/admin/v1/hospital-care/knowledge-bases/${profileId}/`,
    { data: { version }, ...withIdempotency() },
  );
}

export function fetchKnowledgeDocuments(profileId: string) {
  return http.get<unknown, { items: KnowledgeDocumentRow[] }>(
    `/api/admin/v1/hospital-care/knowledge-bases/${profileId}/documents/`,
  );
}

export function createKnowledgeDocument(profileId: string, payload: { title: string; content: string; version: number }) {
  return http.post<unknown, { document: KnowledgeDocumentRow; knowledge_base: KnowledgeBaseRow }>(
    `/api/admin/v1/hospital-care/knowledge-bases/${profileId}/documents/`,
    payload,
    withIdempotency(),
  );
}

export function updateKnowledgeDocument(
  profileId: string,
  documentId: string,
  payload: { title?: string; content?: string; revision: number },
) {
  return http.patch<unknown, { document: KnowledgeDocumentRow; knowledge_base: KnowledgeBaseRow }>(
    `/api/admin/v1/hospital-care/knowledge-bases/${profileId}/documents/${documentId}/`,
    payload,
    withIdempotency(),
  );
}

export function deleteKnowledgeDocument(profileId: string, documentId: string, revision: number) {
  return http.delete<unknown, { document_id: string; is_deleted: boolean; knowledge_base: KnowledgeBaseRow }>(
    `/api/admin/v1/hospital-care/knowledge-bases/${profileId}/documents/${documentId}/`,
    { data: { revision }, ...withIdempotency() },
  );
}

export function buildKnowledgeVector(profileId: string, payload: { version: number; embedding_binding_id: number }) {
  return http.post<unknown, KnowledgeBaseRow>(
    `/api/admin/v1/hospital-care/knowledge-bases/${profileId}/vector-build/`,
    payload,
    withIdempotency(),
  );
}

export function fetchHospitalAuditLogs(hospitalId: string, params: { page: number; page_size: number; action?: string }) {
  return http.get<unknown, { items: HospitalAuditRow[]; pagination: Pagination }>(hospitalUrl(hospitalId, '/audit-logs/'), {
    params,
  });
}
