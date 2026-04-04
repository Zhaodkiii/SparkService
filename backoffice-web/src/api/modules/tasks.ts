import http from '../http';

export interface TaskSummaryResponse {
  summary: {
    window_hours: number;
    total_recent: number;
    status_counter: Record<string, number>;
    periodic_total: number;
    periodic_enabled: number;
  };
  recent_tasks: Array<{
    task_id: string;
    task_name: string;
    status: string;
    date_done: string;
    result: string;
    traceback: string;
  }>;
}

export function fetchTaskDashboard() {
  return http.get<unknown, TaskSummaryResponse>('/api/admin/v1/tasks/dashboard/');
}
