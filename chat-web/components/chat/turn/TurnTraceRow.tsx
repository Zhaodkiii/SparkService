"use client";

import { CheckCircle2, CircleAlert, Loader2, XCircle } from "lucide-react";
import type { ToolActivityDTO } from "@/types/tool";
import { projectToolTrace } from "@/lib/chat/activity-projection";
import type { ToolTraceViewModel } from "@/lib/chat/activity-projection";

function rowIcon(status: ToolActivityDTO["status"]) {
  if (status === "running" || status === "requested") return <Loader2 size={13} className="turn-trace__spin" aria-hidden="true" />;
  if (status === "completed") return <CheckCircle2 size={13} aria-hidden="true" />;
  if (status === "failed") return <CircleAlert size={13} aria-hidden="true" />;
  return <XCircle size={13} aria-hidden="true" />;
}

/**
 * 单条工具调用轨迹 Row：一个 tool_call_id 只渲染一条。动作动词不截断，
 * 脱敏 Chip 可截断；原始 arguments 不进入 DOM。
 */
export function TurnTraceRow({ activity }: { activity: ToolActivityDTO }) {
  const view: ToolTraceViewModel = projectToolTrace(activity);
  const summary = view.errorLine ?? view.resultLine;
  const canExpand = view.isTerminal && Boolean(view.detail) && view.detail !== summary;
  const row = <>
    <span className="turn-trace__icon">{rowIcon(activity.status)}</span>
    <strong className="turn-trace__verb">{view.verb}</strong>
    {view.chip && <span className="turn-trace__chip">{view.chip}</span>}
    {summary && <span className="turn-trace__summary">{summary}</span>}
    {!summary && <span className="turn-trace__summary turn-trace__summary--muted">{view.statusLabel}</span>}
  </>;
  if (!canExpand) return <li className={`turn-trace turn-trace--${view.tone}`}>{row}</li>;
  return <li className={`turn-trace turn-trace--${view.tone}`}>
    <details className="turn-trace__details">
      <summary className="turn-trace__details-summary">{row}</summary>
      <p className="turn-trace__details-body">{view.detail}</p>
    </details>
  </li>;
}
