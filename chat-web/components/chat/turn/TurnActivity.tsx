"use client";

import { useRef, useState } from "react";
import { ChevronDown, Wrench } from "lucide-react";
import type { ChatBlockDTO, TurnActivityViewModel, TurnTraceNode } from "@/types/chat";
import { PublicThinkingCard } from "@/components/chat/turn/PublicThinkingCard";
import { TurnTrace } from "@/components/chat/turn/TurnTrace";
import { formatTurnDuration } from "@/lib/chat/turn-presentation";
import { blockValueObject, blockValue } from "@/components/chat/blocks/common";
import { markForPhase } from "@/components/chat/turn/marks";
import { useTurnElapsedSeconds } from "@/hooks/useTurnElapsedSeconds";

interface TurnActivityProps {
  activity: TurnActivityViewModel;
  thinkingBlocks: ChatBlockDTO[];
  traceNodes: TurnTraceNode[];
  durationMs?: number | null;
  startedAt?: string | null;
  activityId?: string;
}

/**
 * 回合活动头部：助手回合的唯一状态标识。运行中 / 工具中默认展开；首个最终
 * 答案 Delta 到达后自动折叠；失败/中断/取消默认展开。用户手动切换后优先尊重
 * 其选择，且不写入 Message/Block/LocalStorage。
 */
export function TurnActivity({ activity, thinkingBlocks, traceNodes, durationMs, startedAt, activityId }: TurnActivityProps) {
  const toolCount = traceNodes.filter((node) => node.kind === "tool").length;
  const visible = activity.isRunning || activity.isTerminal || traceNodes.length > 0 || thinkingBlocks.length > 0 || durationMs != null;
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const userToggledRef = useRef(false);
  const expanded = userOpen ?? activity.autoExpanded;

  const elapsedMs = useTurnElapsedSeconds(startedAt, activity.isRunning);

  if (!visible) return null;

  const hasThinking = thinkingBlocks.some((block) => {
    const value = blockValue(block);
    if (typeof value === "string") return Boolean(value.trim());
    const object = blockValueObject(block);
    return Object.values(object).some((item) => typeof item === "string" && item.trim());
  });
  const traceHasPublicReasoning = traceNodes.some((node) => node.kind === "round" && Boolean(node.round.public_summary.trim()));
  const showThinkingCards = hasThinking && !traceHasPublicReasoning;
  const expandable = traceNodes.length > 0 || hasThinking;
  const duration = activity.isTerminal ? formatTurnDuration(durationMs) : (elapsedMs != null ? formatTurnDuration(elapsedMs) : null);

  const toggle = () => {
    if (!expandable) return;
    userToggledRef.current = true;
    setUserOpen((value) => !(value ?? activity.autoExpanded));
  };

  const Mark = markForPhase(activity.phase);
  const bodyId = `turn-activity-body-${activityId ?? activity.runId ?? "turn"}`;
  const markClassName = activity.isRunning ? "turn-activity__mark" : undefined;
  const toneClass = activity.phase === "failed" ? " turn-activity--failed" : activity.phase === "cancelled" ? " turn-activity--cancelled" : "";
  const runningClass = activity.isRunning ? " turn-activity--running" : "";
  const headerClass = `turn-activity__header${expandable ? "" : " turn-activity__header--static"}`;

  const headerInner = <>
    <span className="turn-activity__state" aria-hidden="true">
      <Mark size={22} className={markClassName} />
    </span>
    <span className="turn-activity__label">{activity.publicStatusLabel}</span>
    {duration && <span className="turn-activity__duration">· {duration}</span>}
    {toolCount > 0 && <span className="turn-activity__count"><Wrench size={11} aria-hidden="true" />{toolCount}</span>}
    {expandable && <ChevronDown size={15} className={`turn-activity__chevron${expanded ? " turn-activity__chevron--open" : ""}`} aria-hidden="true" />}
  </>;

  return <div className={`turn-activity${expanded ? " turn-activity--open" : ""}${runningClass}${toneClass}`}>
    {expandable ? <button
      type="button"
      className={headerClass}
      aria-expanded={expanded}
      aria-controls={bodyId}
      onClick={toggle}
    >
      {headerInner}
    </button> : <div className={headerClass} role="status" aria-live="polite">
      {headerInner}
    </div>}
    {expandable && <div id={bodyId} className={`turn-activity__body${expanded ? " turn-activity__body--open" : ""}`}>
      <div className="turn-activity__body-inner">
        {showThinkingCards && <div className="turn-activity__thinking">{thinkingBlocks.map((block) => <PublicThinkingCard block={block} key={block.id} />)}</div>}
        <TurnTrace nodes={traceNodes} />
      </div>
    </div>}
  </div>;
}
