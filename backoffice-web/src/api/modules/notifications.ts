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
  delivery_id: number | null;
  business_scene: string;
  business_domain: string;
  business_type: string;
  business_id: string;
  campaign: number | null;
  campaign_name: string;
  user: number | null;
  user_name: string | null;
  recipient_type: 'user' | 'contact' | 'unknown';
  recipient_display: string;
  account_identifier: string;
  recipient_key: string;
  channel: 'apns' | 'email' | 'sms' | 'in_app';
  status: 'queued' | 'processing' | 'accepted' | 'delivered' | 'sent' | 'failed' | 'partial' | 'skipped';
  title: string;
  body: string;
  payload: Record<string, unknown>;
  delivery_details: Array<Record<string, unknown>>;
  target_count: number;
  success_count: number;
  failure_count: number;
  receiver_email: string;
  receiver_phone: string;
  masked_phone: string;
  apns_topic: string;
  template_code: string;
  submit_status: string;
  delivery_status: string;
  code_err_code: string;
  biz_id: string;
  provider_message_id: string;
  provider_request_id: string;
  provider_code: string;
  provider_status: string;
  error_message: string;
  request_id: string;
  submitted_at: string | null;
  receipt_at: string | null;
  sent_at: string | null;
  delivered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationLogListResponse {
  items: NotificationMessageLog[];
  pagination: Pagination;
}

export interface NotificationOverview {
  window_days: number;
  since: string;
  summary: {
    message_total: number;
    message_sent: number;
    message_failed: number;
    message_partial: number;
    message_skipped: number;
    delivery_total: number;
    delivery_delivered: number;
    delivery_accepted: number;
    delivery_failed: number;
    delivery_submit_failed: number;
    delivery_submit_unknown: number;
    delivery_cancelled: number;
    delivery_expired: number;
  };
  by_channel: Record<string, { messages: number; deliveries: number; delivered: number; failed: number }>;
  recent_messages: Array<{
    id: number;
    campaign_id: number | null;
    channel: 'apns' | 'email' | 'sms';
    status: 'queued' | 'processing' | 'accepted' | 'delivered' | 'sent' | 'failed' | 'partial' | 'skipped';
    title: string;
    recipient: string;
    request_id: string;
    created_at: string;
  }>;
}

export interface NotificationSuppression {
  id: number;
  endpoint_hmac: string;
  user: number | null;
  user_name: string | null;
  channel: 'apns' | 'email' | 'sms' | 'all';
  reason: 'user_opt_out' | 'hard_bounce' | 'complaint' | 'invalid_endpoint' | 'policy';
  detail: string;
  expires_at: string | null;
  created_by: number | null;
  created_by_name: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotificationSuppressionListResponse {
  items: NotificationSuppression[];
  pagination: Pagination;
}

export interface NotificationAnalytics {
  window_days: number;
  since: string;
  summary: {
    messages: number;
    deliveries: number;
    provider_events: number;
    suppressions: number;
  };
  channel_stats: Array<{
    channel: 'apns' | 'email' | 'sms';
    message_total: number;
    delivery_total: number;
    delivered: number;
    failed: number;
    success_rate: number;
    failure_rate: number;
  }>;
  message_status_stats: Array<Record<string, string | number>>;
  delivery_status_stats: Array<Record<string, string | number>>;
  provider_event_stats: Array<Record<string, string | number>>;
  suppression_reason_stats: Array<Record<string, string | number>>;
}

export interface NotificationChannelSetting {
  channel: 'apns' | 'sms' | 'email';
  name: string;
  enabled: boolean;
  environment: string;
  config: Record<string, string | number | boolean | null>;
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
  return http.get<unknown, NotificationUserListResponse>('/api/admin/v1/notification-center/notifications/users/', { params });
}

export function fetchNotificationOverview(params?: { window_days?: number }) {
  return http.get<unknown, NotificationOverview>('/api/admin/v1/notification-center/overview/', { params });
}

export function fetchNotificationTemplates() {
  return http.get<unknown, NotificationTemplate[]>('/api/admin/v1/notification-center/notifications/templates/');
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
  return http.post<unknown, NotificationTemplate>('/api/admin/v1/notification-center/notifications/templates/', payload);
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
  return http.patch<unknown, NotificationTemplate>(`/api/admin/v1/notification-center/notifications/templates/${templateId}/`, payload);
}

export function deleteNotificationTemplate(templateId: number) {
  return http.delete(`/api/admin/v1/notification-center/notifications/templates/${templateId}/`);
}

export function previewNotification(payload: {
  template_id?: number | null;
  user_id?: number | null;
  title?: string;
  body?: string;
  payload?: Record<string, unknown>;
}) {
  return http.post<unknown, { title: string; body: string; payload: Record<string, unknown>; context: Record<string, string> }>(
    '/api/admin/v1/notification-center/notifications/preview/',
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
  return http.post<unknown, NotificationCampaign>('/api/admin/v1/notification-center/notifications/send/', payload);
}

export function fetchNotificationCampaigns(params: { page: number; page_size: number; q?: string; status?: string }) {
  return http.get<unknown, NotificationCampaignListResponse>('/api/admin/v1/notification-center/notifications/campaigns/', { params });
}

export function fetchNotificationLogs(
  channel: 'all' | 'apns' | 'email' | 'sms',
  params: { page: number; page_size: number; q?: string; status?: '' | 'queued' | 'processing' | 'accepted' | 'delivered' | 'sent' | 'failed' | 'partial' | 'skipped' },
) {
  return http.get<unknown, NotificationLogListResponse>(`/api/admin/v1/notification-center/notifications/records/${channel}/`, { params });
}

export function fetchNotificationLogDetail(logId: number) {
  return http.get<unknown, NotificationMessageLog>(`/api/admin/v1/notification-center/notifications/logs/detail/${logId}/`);
}

export function querySmsSendDetails(logId: number) {
  return http.post<unknown, NotificationMessageLog>(`/api/admin/v1/notification-center/notifications/sms-records/${logId}/query-send-details/`);
}

export function fetchNotificationSuppressions(params: {
  page: number;
  page_size: number;
  q?: string;
  channel?: '' | 'apns' | 'email' | 'sms' | 'all';
  reason?: string;
  only_active?: boolean;
}) {
  return http.get<unknown, NotificationSuppressionListResponse>('/api/admin/v1/notification-center/notifications/suppressions/', { params });
}

export function releaseNotificationSuppression(suppressionId: number) {
  return http.post<unknown, NotificationSuppression>(`/api/admin/v1/notification-center/notifications/suppressions/${suppressionId}/release/`);
}

export function fetchNotificationAnalytics(params?: { window_days?: number }) {
  return http.get<unknown, NotificationAnalytics>('/api/admin/v1/notification-center/analytics/', { params });
}

export function fetchNotificationChannelSettings() {
  return http.get<unknown, { channels: NotificationChannelSetting[] }>('/api/admin/v1/notification-center/channel-settings/');
}
