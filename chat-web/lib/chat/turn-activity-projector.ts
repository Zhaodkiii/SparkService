import type { ChatRunStatus, TurnActivityPhase, TurnActivityViewModel } from "@/types/chat";
import { isTerminalRunStatus } from "@/types/chat";
import type { ToolActivityDTO } from "@/types/tool";
import { isTerminalToolActivityStatus } from "@/types/tool";

/**
 * Turn activity projector：把公开的 Run/assistant.status/工具活动投影为可展示的
 * 回合状态模型。这里只做 allowlist 映射，绝不读取 raw reasoning、raw arguments
 * 或 raw result；未知状态一律降级为通用文案。
 */

export interface TurnActivityInput {
  runId: string | null;
  runStatus: ChatRunStatus | null;
  assistantStatus: string | null;
  toolRows: ToolActivityDTO[];
  contentStreaming: boolean;
}

/** 公开 assistant.status allowlist → 用户可见阶段文案。 */
const PUBLIC_ASSISTANT_STATUS_LABELS: Record<string, string> = {
  idle: "准备开始",
  thinking: "小鲸探索中…",
  searching: "小鲸探索中…",
  exploring: "小鲸探索中…",
  using_tools: "正在调用工具…",
  composing: "小鲸正在回答…",
};

const PHASE_LABELS: Record<TurnActivityPhase, string> = {
  exploring: "小鲸探索中…",
  using_tools: "正在调用工具…",
  composing: "小鲸正在回答…",
  waiting: "等待回复",
  completed: "已完成",
  failed: "生成失败",
  cancelled: "已停止",
  interrupted: "已中断",
};

function derivePhase(input: TurnActivityInput): TurnActivityPhase {
  const { runStatus, toolRows, contentStreaming } = input;
  if (!runStatus) return "completed";
  if (runStatus === "waiting_for_user_input" || runStatus === "waiting_for_client_tool") return "waiting";
  if (isTerminalRunStatus(runStatus)) {
    if (runStatus === "failed") return "failed";
    if (runStatus === "cancelled") return "cancelled";
    if (runStatus === "interrupted") return "interrupted";
    return "completed";
  }
  if (toolRows.some((row) => !isTerminalToolActivityStatus(row.status))) return "using_tools";
  if (contentStreaming) return "composing";
  return "exploring";
}

function publicStatusLabel(input: TurnActivityInput, phase: TurnActivityPhase): string {
  const { assistantStatus, runStatus } = input;
  if (runStatus === "waiting_for_user_input") return "等待你的回复";
  if (runStatus === "waiting_for_client_tool") return "等待设备授权";
  if (runStatus === "unknown") return "正在处理";
  if (!runStatus || isTerminalRunStatus(runStatus)) return PHASE_LABELS[phase];
  const mapped = assistantStatus ? PUBLIC_ASSISTANT_STATUS_LABELS[assistantStatus] : null;
  return mapped ?? PHASE_LABELS[phase];
}

function autoExpanded(phase: TurnActivityPhase, isRunning: boolean): boolean {
  if (phase === "failed" || phase === "cancelled" || phase === "interrupted") return true;
  if (phase === "composing" || phase === "completed") return false;
  return isRunning;
}

export function projectTurnActivity(input: TurnActivityInput): TurnActivityViewModel {
  const phase = derivePhase(input);
  const isRunning = input.runStatus !== null && !isTerminalRunStatus(input.runStatus);
  const isTerminal = input.runStatus === null || isTerminalRunStatus(input.runStatus);
  const anyToolRunning = input.toolRows.some((row) => !isTerminalToolActivityStatus(row.status));
  return {
    runId: input.runId,
    runStatus: input.runStatus,
    phase,
    publicStatusLabel: publicStatusLabel(input, phase),
    toolRows: input.toolRows,
    hasToolActivity: input.toolRows.length > 0,
    anyToolRunning,
    isRunning,
    isTerminal,
    isFinalAnswerPhase: phase === "composing",
    autoExpanded: autoExpanded(phase, isRunning),
  };
}
