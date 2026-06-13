import http from '../http';
import type { Pagination } from '../../types';
import type { AxiosRequestConfig } from 'axios';

export interface MedicalDataMeta {
  duration_ms: number;
  cache_hit: boolean;
  stats_status: string;
  generated_at: string;
}

export interface MedicalDataPermissions {
  can_view_sensitive: boolean;
  can_view_raw_json: boolean;
  can_view_attachment: boolean;
  can_download_attachment: boolean;
}

export interface MedicalDataGlobalStats {
  users_with_medical_data: number;
  users_with_ai_recognition: number;
  medical_data_total: number;
  attachment_total: number;
  stats_status?: string;
  refreshed_at?: string | null;
  cache_hit?: boolean;
}

export interface MedicalDataUserRow {
  user_id: number;
  username: string;
  raw_username: string;
  email: string;
  phone: string;
  is_active: boolean;
  user_status: string;
  is_anonymized: boolean;
  date_joined: string | null;
  last_login: string | null;
  member_count: number;
  members_with_data_count: number;
  medical_data_total: number;
  attachment_count: number;
  ai_task_count: number;
  last_updated_at: string | null;
  last_source: string;
  risk_flags: string[];
  stats_status?: string;
  quality_flag_count?: number;
}

export interface MedicalDataUserListResponse {
  items: MedicalDataUserRow[];
  pagination: Pagination;
  permissions: MedicalDataPermissions;
  meta?: MedicalDataMeta;
}

export interface MedicalDataGlobalStatsResponse {
  stats: MedicalDataGlobalStats;
  meta?: MedicalDataMeta;
}

export interface MedicalDataMemberRow {
  member_id: number;
  binding_id: number;
  name: string;
  raw_name: string;
  relationship: string;
  relationship_label: string;
  gender: string;
  gender_label: string;
  birth_date: string;
  age: number | null;
  is_primary: boolean;
  binding_role: string;
  binding_role_label: string;
  binding_status: string;
  can_edit: boolean;
  shared_user_count: number;
  share_summary: string;
  medical_case_count: number;
  health_exam_report_count: number;
  examination_report_count: number;
  medicine_box_count: number;
  prescription_count: number;
  medication_plan_count: number;
  symptom_count: number;
  visit_count: number;
  surgery_count: number;
  follow_up_count: number;
  attachment_count: number;
  total_count: number;
  has_data: boolean;
  last_updated_at: string | null;
  medication_summary: {
    today_total: number;
    today_taken: number;
    today_skipped: number;
    today_pending: number;
    adherence_rate: number;
  };
  stats_status?: string;
}

export interface MedicalDataUserSummary {
  user_id: number;
  username: string;
  email: string;
  is_active: boolean;
  user_status: string;
  date_joined: string | null;
  last_login: string | null;
  member_count: number;
  members_with_data_count: number;
  medical_data_total: number;
  attachment_count: number;
  ai_task_count: number;
  last_updated_at: string | null;
  last_source: string;
  stats_status?: string;
}

export interface MedicalDataMembersResponse {
  user: MedicalDataUserSummary;
  members: MedicalDataMemberRow[];
  pagination: Pagination;
  permissions: MedicalDataPermissions;
  meta?: MedicalDataMeta;
}

export interface MedicalDataQualityFlag {
  type: string;
  resource_type: string;
  resource_id: number;
  message: string;
}

export interface MedicalDataTimelineEvent {
  date: string;
  type: string;
  resource_id: number;
  title: string;
}

export interface MedicalDataSharedRelation {
  binding_id: number;
  user_id: number;
  username: string;
  email: string;
  relationship: string;
  relationship_label: string;
  role: string;
  role_label: string;
  is_owner: boolean;
  share_source: string;
  status: string;
  status_label: string;
  created_at: string;
  updated_at: string;
}

export interface MedicalDataCompleteResponse {
  member_id: number;
  entry_user_id: number;
  member: MedicalDataMemberRow;
  category_counts: Record<string, number>;
  medication_summary: MedicalDataMemberRow['medication_summary'];
  source_summary: Record<string, number>;
  ai_task_summary: Record<string, number>;
  quality_flag_count: number;
  shared_relations_summary: { active_binding_count: number };
  permissions: MedicalDataPermissions;
  meta?: MedicalDataMeta;
}

export interface MedicalDataResourceListResponse {
  resource_type: string;
  member_id: number;
  items: Record<string, unknown>[];
  pagination: Pagination;
  permissions: MedicalDataPermissions;
  meta?: MedicalDataMeta;
}

export interface MedicalDataResourceDetail {
  resource_type: string;
  resource_id: number;
  basic: Record<string, unknown>;
  med_exam_details: Record<string, unknown>[];
  attachments: Record<string, unknown>[];
  ai_info: Record<string, unknown>;
  related: Record<string, unknown>;
  audit: Record<string, unknown>;
  raw_json: Record<string, unknown> | null;
}

export type MedicalResourceType =
  | 'medical-cases'
  | 'health-exam-reports'
  | 'examination-reports'
  | 'medicine-boxes'
  | 'family-medicine-boxes'
  | 'prescriptions'
  | 'medication-plans'
  | 'medication-records'
  | 'symptoms'
  | 'visits'
  | 'surgeries'
  | 'follow-ups'
  | 'attachments';

export interface MedicalDataUserListQuery {
  page: number;
  page_size: number;
  user_id?: string;
  keyword?: string;
  data_type?: string;
  source?: string;
  has_attachment?: string;
  has_ai_task?: string;
  updated_after?: string;
  updated_before?: string;
  status?: string;
  ordering?: string;
}

type RequestConfig = AxiosRequestConfig & { signal?: AbortSignal };

export function fetchMedicalDataGlobalStats(config?: RequestConfig) {
  return http.get<unknown, MedicalDataGlobalStatsResponse>('/api/admin/v1/medical-data/stats/global/', config);
}

export function fetchMedicalDataUsers(params: MedicalDataUserListQuery, config?: RequestConfig) {
  return http.get<unknown, MedicalDataUserListResponse>('/api/admin/v1/medical-data/users/', { params, ...config });
}

export function fetchMedicalDataUserMembers(
  userId: number,
  params?: { include_empty?: string; only_with_data?: string; page?: number; page_size?: number },
  config?: RequestConfig,
) {
  return http.get<unknown, MedicalDataMembersResponse>(`/api/admin/v1/medical-data/users/${userId}/members/`, {
    params,
    ...config,
  });
}

export function fetchMedicalDataComplete(userId: number, memberId: number, config?: RequestConfig) {
  return http.get<unknown, MedicalDataCompleteResponse>(
    `/api/admin/v1/medical-data/users/${userId}/members/${memberId}/complete-data/`,
    config,
  );
}

export function fetchMedicalDataTimeline(
  userId: number,
  memberId: number,
  params?: { page?: number; page_size?: number; limit?: number },
  config?: RequestConfig,
) {
  return http.get<unknown, { items: MedicalDataTimelineEvent[]; pagination: Pagination; meta?: MedicalDataMeta }>(
    `/api/admin/v1/medical-data/users/${userId}/members/${memberId}/timeline/`,
    { params, ...config },
  );
}

export function fetchMedicalDataQualityFlags(
  userId: number,
  memberId: number,
  params?: { page?: number; page_size?: number },
  config?: RequestConfig,
) {
  return http.get<unknown, { items: MedicalDataQualityFlag[]; pagination: Pagination; meta?: MedicalDataMeta }>(
    `/api/admin/v1/medical-data/users/${userId}/members/${memberId}/quality-flags/`,
    { params, ...config },
  );
}

export function fetchMedicalDataSharedRelations(
  userId: number,
  memberId: number,
  includeHistory = false,
  config?: RequestConfig,
) {
  return http.get<unknown, { items: MedicalDataSharedRelation[]; pagination?: Pagination }>(
    `/api/admin/v1/medical-data/users/${userId}/members/${memberId}/shared-relations/`,
    { params: { include_history: includeHistory ? 'true' : 'false' }, ...config },
  );
}

export function fetchMedicalDataResources(
  userId: number,
  memberId: number,
  resourceType: MedicalResourceType,
  params: { page: number; page_size: number; keyword?: string },
  config?: RequestConfig,
) {
  return http.get<unknown, MedicalDataResourceListResponse>(
    `/api/admin/v1/medical-data/users/${userId}/members/${memberId}/${resourceType}/`,
    { params, ...config },
  );
}

export function fetchMedicalDataResourceDetail(resourceType: string, resourceId: number, config?: RequestConfig) {
  return http.get<unknown, MedicalDataResourceDetail>(
    `/api/admin/v1/medical-data/resources/${resourceType}/${resourceId}/`,
    config,
  );
}

export function fetchMedicalDataAttachmentDownload(fileId: number, config?: RequestConfig) {
  return http.get<unknown, { url: string; expires_in_seconds: number; file_id: number }>(
    `/api/admin/v1/medical-data/attachments/${fileId}/download/`,
    config,
  );
}

export const MEDICAL_RESOURCE_TABS: Array<{ key: MedicalResourceType | 'overview' | 'timeline'; label: string }> = [
  { key: 'overview', label: '总览' },
  { key: 'medical-cases', label: '病例' },
  { key: 'health-exam-reports', label: '体检报告' },
  { key: 'examination-reports', label: '检查检验' },
  { key: 'medicine-boxes', label: '药盒' },
  { key: 'family-medicine-boxes', label: '家庭药箱' },
  { key: 'prescriptions', label: '处方' },
  { key: 'medication-plans', label: '用药计划' },
  { key: 'medication-records', label: '用药记录' },
  { key: 'symptoms', label: '症状' },
  { key: 'visits', label: '就诊' },
  { key: 'surgeries', label: '手术' },
  { key: 'follow-ups', label: '随访' },
  { key: 'attachments', label: '附件' },
  { key: 'timeline', label: '时间线' },
];

export const DATA_TYPE_OPTIONS = [
  { value: '', label: '全部类型' },
  { value: 'medical_case', label: '病例' },
  { value: 'health_exam', label: '体检' },
  { value: 'examination', label: '检查' },
  { value: 'medicine_box', label: '药盒' },
  { value: 'prescription', label: '处方' },
  { value: 'medication_plan', label: '用药计划' },
  { value: 'symptom', label: '症状' },
  { value: 'visit', label: '就诊' },
  { value: 'surgery', label: '手术' },
  { value: 'follow_up', label: '随访' },
];
