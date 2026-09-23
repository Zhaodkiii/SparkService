import http from '../http';

export interface SubscriptionSource {
  type: string;
  active: boolean;
  environment?: string | null;
  entitlement?: string | null;
  product_id?: string | null;
  expires_at?: string | null;
  will_renew?: boolean | null;
  status?: string | null;
  billing_status?: string | null;
  pending_product_id?: string | null;
  revoked_at?: string | null;
  store?: string | null;
  last_synced_at?: string | null;
}

export interface SubscriptionSummary {
  is_pro: boolean;
  effective_source: string;
  sync_state: string;
  last_synced_at: string | null;
  sources: SubscriptionSource[];
}

export interface SubscriptionSnapshot {
  entitlement_identifier: string;
  environment: string;
  status: string;
  product_id: string;
  expires_at: string | null;
  will_renew: boolean;
  last_synced_at: string;
}

export interface SubscriptionUserDetail {
  user_id: number;
  summary: SubscriptionSummary;
  snapshots: SubscriptionSnapshot[];
  ownerships?: SubscriptionOwnership[];
  ownership_conflict_count?: number;
}

export interface SubscriptionOwnership {
  store: string;
  environment: string;
  state: string;
  first_product_id: string;
  first_bound_at: string;
  last_verified_at: string;
  tombstoned_at: string | null;
}

export interface SubscriptionWebhookEvent {
  event_id: string;
  event_type: string;
  environment: string;
  process_status: string;
  attempt_count: number;
  matched_user_id: number | null;
  error_code: string;
  received_at: string;
  processed_at: string | null;
}

export interface SubscriptionEventListResponse {
  items: SubscriptionWebhookEvent[];
  page: number;
  page_size: number;
  total: number;
}

export function fetchSubscriptionUser(userId: number) {
  return http.get<unknown, SubscriptionUserDetail>(`/api/admin/v1/subscriptions/users/${userId}/`);
}

export function synchronizeSubscriptionUser(userId: number) {
  return http.post<unknown, SubscriptionSummary>(`/api/admin/v1/subscriptions/users/${userId}/sync/`);
}

export function fetchSubscriptionEvents(params: {
  page: number;
  page_size: number;
  user_id?: number;
  process_status?: string;
  environment?: string;
}) {
  return http.get<unknown, SubscriptionEventListResponse>('/api/admin/v1/subscriptions/events/', { params });
}

export function replaySubscriptionEvent(eventId: string) {
  return http.post(`/api/admin/v1/subscriptions/events/${encodeURIComponent(eventId)}/replay/`);
}
