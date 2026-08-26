import http from '../http';

export interface TaskSummaryResponse {
  summary: {
    window_hours: number;
    total_recent: number;
    status_counter: Record<string, number>;
    periodic_total: number;
    periodic_enabled: number;
    periodic_disabled: number;
    failure_rate: number;
    running_like: number;
    business_counter: {
      notification: {
        total: number;
        success: number;
        failure: number;
        running: number;
      };
      deactivation: {
        total: number;
        success: number;
        failure: number;
        running: number;
      };
    };
  };
  recent_tasks: Array<{
    task_id: string;
    task_name: string;
    status: string;
    date_done: string;
    result: string;
    result_preview: string;
    has_traceback: boolean;
    traceback: string;
  }>;
}

export function fetchTaskDashboard(params?: { window_hours?: number; limit?: number }) {
  return http.get<unknown, TaskSummaryResponse>('/api/admin/v1/tasks/dashboard/', { params });
}

export interface TaskManagerStatusResponse {
  host: string;
  worker: { pid: number | null; running: boolean };
  beat: { pid: number | null; running: boolean };
  overall_running: boolean;
  ping: {
    healthy: boolean;
    returncode: number;
    output: string;
    error: string;
  };
  redis: {
    healthy: boolean;
    display: string;
    error: string;
    local_manageable?: boolean;
    /** @deprecated 与 local_manageable 相同，兼容旧后端 */
    local_start_available?: boolean;
  };
  worker_queues?: string[];
  chat_ai?: {
    server_runs_enabled: boolean;
    run_executor: string;
  };
  run_dir: string;
  log_dir: string;
}

export interface TaskManagerControlResponse {
  action: 'start' | 'stop' | 'restart' | 'start_redis' | 'stop_redis';
  operations: Array<{ name: string; action: string; pid?: number }>;
  status: TaskManagerStatusResponse;
}

export function fetchTaskManagerStatus() {
  return http.get<unknown, TaskManagerStatusResponse>('/api/admin/v1/tasks/manager/status/');
}

export function controlTaskManager(action: 'start' | 'stop' | 'restart' | 'start_redis' | 'stop_redis') {
  return http.post<unknown, TaskManagerControlResponse>(`/api/admin/v1/tasks/manager/${action}/`, {});
}
