"use client";

import { useState } from "react";
import { CheckCircle2, ChevronDown, CircleAlert, Database, Loader2, XCircle } from "lucide-react";
import type { ChatBlockDTO } from "@/types/chat";
import type { ToolActivityDTO } from "@/types/tool";
import { projectToolActivity } from "@/lib/chat/activity-projection";

function toneIcon(status: ToolActivityDTO["status"]) {
  if (status === "running" || status === "requested") return <Loader2 size={14} className="tool-disclosure__spin" />;
  if (status === "completed") return <CheckCircle2 size={14} />;
  if (status === "failed") return <CircleAlert size={14} />;
  return <XCircle size={14} />;
}

/**
 * Inline, collapsed-by-default disclosure for one server tool call. Shows only
 * the safe projection (display args labels, server-generated preview, error
 * copy). Raw tool data never reaches this component by contract.
 */
export function ToolActivityDisclosure({ block, activity }: { block: ChatBlockDTO; activity: ToolActivityDTO | null }) {
  const [open, setOpen] = useState(false);
  const view = activity ? projectToolActivity(activity) : null;
  const fallback = typeof block.payload?.fallback_text === "string" ? block.payload.fallback_text : null;
  const title = view?.displayName ?? (block.kind === "toolResult" ? "工具执行结束" : "服务端工具");
  const summary = view
    ? view.errorLine ?? view.resultLine ?? view.statusLabel
    : fallback ?? (block.kind === "toolResult" ? "结果已记录" : "执行中");
  const hasDetail = Boolean(view && (view.argSummary || view.errorLine || view.sourceCount > 0 || view.duplicate));
  const status = activity?.status ?? (block.status === "failed" ? "cancelled" : "requested");

  return <div className={`tool-disclosure tool-disclosure--${view?.tone ?? status}`}>
    <button type="button" className="tool-disclosure__header" aria-expanded={open} onClick={() => setOpen((value) => !value)} disabled={!hasDetail}>
      <span className={`tool-disclosure__icon tool-disclosure__icon--${view?.tone ?? status}`}>{toneIcon(status)}</span>
      <span className="tool-disclosure__title">{title}</span>
      <span className="tool-disclosure__summary">{summary}</span>
      {hasDetail && <ChevronDown size={13} className={`tool-disclosure__chevron${open ? " tool-disclosure__chevron--open" : ""}`} />}
    </button>
    {open && hasDetail && view && (
      <div className="tool-disclosure__detail">
        {view.argSummary && <p><Database size={12} />{view.argSummary}</p>}
        {view.duplicate && <p>已复用相同请求的结果</p>}
        {view.sourceCount > 0 && (
          <div className="knowledge-citations">
            <p>已引用 {view.sourceCount} 条资料</p>
            <ul>
              {(activity?.source_refs ?? []).map((ref) => (
                <li key={ref.source_id}>
                  {ref.type === "knowledge_chunk" && ref.title ? (
                    <span>当时版本 · {ref.title}</span>
                  ) : (
                    <span>{ref.title || ref.source_id}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        {view.errorLine && <p className="tool-disclosure__error">{view.errorLine}{view.retryable ? "，可重试" : ""}</p>}
      </div>
    )}
  </div>;
}
