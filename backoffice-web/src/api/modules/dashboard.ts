import http from '../http';

export interface DashboardOverview {
  users: { total: number; active: number; staff: number };
  files: { managed: number; public: number };
  deactivation: { requested: number; failed: number };
}

export function fetchDashboardOverview() {
  return http.get<unknown, DashboardOverview>('/api/admin/v1/dashboard/overview/');
}
