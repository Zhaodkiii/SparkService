import http from '../http';
import type { Pagination } from '../../types';

export interface NotificationUserRow {
  id: number;
  username: string;
  email: string;
  phone_number: string;
  is_active: boolean;
  date_joined: string;
  last_login: string | null;
  total_devices: number;
  enabled_push_devices: number;
  channels: {
    apns: boolean;
    email: boolean;
    sms: boolean;
  };
}

export interface NotificationUserListResponse {
  items: NotificationUserRow[];
  pagination: Pagination;
}

export interface NotificationTemplate {
  id: number;
  name: string;
  description: string;
  title_template: string;
  body_template: string;
  payload_template: Record<string, unknown>;
  default_channels: Array<'apns' | 'email' | 'sms'>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotificationCampaign {
  id: number;
  name: string;
  status: 'queued' | 'scheduled' | 'running' | 'completed' | 'failed';
  channels: Array<'apns' | 'email' | 'sms'>;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  filters: Record<string, unknown>;
  target_user_ids: number[];
  target_count: number;
  success_count: number;
  failure_count: number;
  template: number | null;
  template_name: string;
  created_by: number | null;
  created_by_name: string;
  task_id: string;
  request_id: string;
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export interface NotificationCampaignListResponse {
  items: NotificationCampaign[];
  pagination: Pagination;
}

export interface NotificationMessageLog {
  id: number;
  campaign: number | null;
  campaign_name: string;
  user: number;
  user_name: string;
  channel: 'apns' | 'email' | 'sms';
  status: 'sent' | 'failed' | 'partial' | 'skipped';
  title: string;
  body: string;
  payload: Record<string, unknown>;
  delivery_details: Array<Record<string, unknown>>;
  target_count: number;
  success_count: number;
  failure_count: number;
  receiver_email: string;
  receiver_phone: string;
  apns_topic: string;
  provider_message_id: string;
  error_message: string;
  request_id: string;
  sent_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationLogListResponse {
  items: NotificationMessageLog[];
  pagination: Pagination;
}

export function fetchNotificationUsers(params: {
  page: number;
  page_size: number;
  q?: string;
  only_enabled?: boolean;
  has_email?: boolean;
  has_sms?: boolean;
  has_apns?: boolean;
  is_active?: boolean;
}) {
  return http.get<unknown, NotificationUserListResponse>('/api/admin/v1/notifications/users/', { params });
}

export function fetchNotificationTemplates() {
  return http.get<unknown, NotificationTemplate[]>('/api/admin/v1/notifications/templates/');
}

export function createNotificationTemplate(payload: {
  name: string;
  description?: string;
  title_template?: string;
  body_template?: string;
  payload_template?: Record<string, unknown>;
  default_channels?: Array<'apns' | 'email' | 'sms'>;
  is_active?: boolean;
}) {
  return http.post<unknown, NotificationTemplate>('/api/admin/v1/notifications/templates/', payload);
}

export function updateNotificationTemplate(templateId: number, payload: Partial<{
  name: string;
  description: string;
  title_template: string;
  body_template: string;
  payload_template: Record<string, unknown>;
  default_channels: Array<'apns' | 'email' | 'sms'>;
  is_active: boolean;
}>) {
  return http.patch<unknown, NotificationTemplate>(`/api/admin/v1/notifications/templates/${templateId}/`, payload);
}

export function deleteNotificationTemplate(templateId: number) {
  return http.delete(`/api/admin/v1/notifications/templates/${templateId}/`);
}

export function previewNotification(payload: {
  template_id?: number | null;
  user_id?: number | null;
  title?: string;
  body?: string;
  payload?: Record<string, unknown>;
}) {
  return http.post<unknown, { title: string; body: string; payload: Record<string, unknown>; context: Record<string, string> }>(
    '/api/admin/v1/notifications/preview/',
    payload,
  );
}

export function createNotificationCampaign(payload: {
  campaign_name?: string;
  template_id?: number | null;
  user_id?: number | null;
  user_ids?: number[];
  title?: string;
  body?: string;
  channels: Array<'apns' | 'email' | 'sms'>;
  filters?: Record<string, unknown>;
  payload?: Record<string, unknown>;
  schedule_at?: string | null;
}) {
  return http.post<unknown, NotificationCampaign>('/api/admin/v1/notifications/send/', payload);
}

export function fetchNotificationCampaigns(params: { page: number; page_size: number; q?: string; status?: string }) {
  return http.get<unknown, NotificationCampaignListResponse>('/api/admin/v1/notifications/campaigns/', { params });
}

export function fetchNotificationLogs(
  channel: 'apns' | 'email' | 'sms',
  params: { page: number; page_size: number; q?: string; status?: '' | 'sent' | 'failed' | 'partial' | 'skipped' },
) {
  return http.get<unknown, NotificationLogListResponse>(`/api/admin/v1/notifications/logs/${channel}/`, { params });
}

export function fetchNotificationLogDetail(logId: number) {
  return http.get<unknown, NotificationMessageLog>(`/api/admin/v1/notifications/logs/detail/${logId}/`);
}
