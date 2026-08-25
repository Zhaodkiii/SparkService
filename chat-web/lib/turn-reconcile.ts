import type { ChatRuntimeState } from "@/types/chat";

export function getActiveRunId(state: ChatRuntimeState, threadId: string): string | null {
  const run = Object.values(state.runsById).find((candidate) => candidate.thread_id === threadId && ["queued", "running", "waiting_for_user_input", "waiting_for_client_tool"].includes(candidate.status));
  return run?.id ?? null;
}

export function getRunBanner(state: ChatRuntimeState, runId: string | null): string | null {
  if (!runId) return null;
  const run = state.runsById[runId];
  if (!run) return "正在恢复运行状态";
  if (state.replayRequiredByRun[runId]) return "正在补齐事件";
  return run.status;
}
