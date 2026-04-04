import http from '../http';

export interface DashboardOverview {
  users: { total: number; active: number; staff: number };
  chat: { threads: number; messages: number };
  medical: { members: number; cases: number };
  files: { managed: number; public: number };
  deactivation: { requested: number; failed: number };
}

export function fetchDashboardOverview() {
  return http.get<unknown, DashboardOverview>('/api/admin/v1/dashboard/overview/');
}
