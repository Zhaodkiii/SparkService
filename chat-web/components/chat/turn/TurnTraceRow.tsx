"use client";

import { CheckCircle2, CircleAlert, Loader2, XCircle } from "lucide-react";
import type { ToolActivityDTO } from "@/types/tool";
import { projectToolActivity, projectToolTrace } from "@/lib/chat/activity-projection";
import type { ToolActivityViewModel, ToolTraceViewModel } from "@/lib/chat/activity-projection";
import { CHAT_DEEPTUTOR_TURN_UI_ENABLED } from "@/lib/feature-flags";

function rowIcon(status: ToolActivityDTO["status"]) {
  if (status === "running" || status === "requested") return <Loader2 size={13} className="turn-trace__spin" aria-hidden="true" />;
  if (status === "completed") return <CheckCircle2 size={13} aria-hidden="true" />;
  if (status === "failed") return <CircleAlert size={13} aria-hidden="true" />;
  return <XCircle size={13} aria-hidden="true" />;
}

function LegacyToolRow({ activity }: { activity: ToolActivityDTO }) {
  const view: ToolActivityViewModel = projectToolActivity(activity);
  const summary = view.errorLine ?? view.resultLine ?? (view.argSummary ? `${view.argSummary} · ${view.statusLabel}` : view.statusLabel);
  return <li className={`turn-trace turn-trace--${view.tone}`}>
    <span className="turn-trace__icon">{rowIcon(activity.status)}</span>
    <strong>{view.displayName}</strong>
    <span className="turn-trace__summary">{summary}</span>
  </li>;
}

/**
 * CHAT-WEB-027 W3: DeepTutor-aligned tool row — action verb anchors the line
 * (never truncates), an optional artifact chip names what it acted on, and
 * a result/error line follows. Terminal calls with extra detail (source
 * count, full error text) become a native `<details>` disclosure so the
 * collapsed row stays compact without losing the information.
 */
function DeepTutorToolRow({ activity }: { activity: ToolActivityDTO }) {
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

/** 单条工具调用轨迹 Row（能力三）：一个 tool_call_id 只渲染一条。 */
export function TurnTraceRow({ activity }: { activity: ToolActivityDTO }) {
  return CHAT_DEEPTUTOR_TURN_UI_ENABLED ? <DeepTutorToolRow activity={activity} /> : <LegacyToolRow activity={activity} />;
}
