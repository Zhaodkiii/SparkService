"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Sparkles, Wrench } from "lucide-react";
import type { ChatBlockDTO, TurnActivityViewModel, TurnTraceNode } from "@/types/chat";
import { PublicThinkingCard } from "@/components/chat/turn/PublicThinkingCard";
import { TurnTrace } from "@/components/chat/turn/TurnTrace";
import { formatTurnDuration } from "@/lib/chat/turn-presentation";
import { blockValueObject, blockValue } from "@/components/chat/blocks/common";
import { markForPhase } from "@/components/chat/turn/marks";
import { useTurnElapsedSeconds } from "@/hooks/useTurnElapsedSeconds";
import { CHAT_DEEPTUTOR_TURN_UI_ENABLED } from "@/lib/feature-flags";

interface TurnActivityProps {
  activity: TurnActivityViewModel;
  thinkingBlocks: ChatBlockDTO[];
  traceNodes: TurnTraceNode[];
  durationMs?: number | null;
  startedAt?: string | null;
  activityId?: string;
}

/**
 * 回合活动头部（能力二/三）：助手工作时显示一条轻量状态头。运行中默认展开，
 * 进入 final answer 或 Run 终态后自动折叠；用户手动切换后优先尊重其选择。
 *
 * DeepTutor-aligned behavior (marks/自动折叠时机/动态计时) is gated by
 * `NEXT_PUBLIC_CHAT_DEEPTUTOR_TURN_UI_ENABLED`; disabled falls back to the
 * pre-existing Sparkles-only, terminal-only-fold renderer.
 */
export function TurnActivity({ activity, thinkingBlocks, traceNodes, durationMs, startedAt, activityId }: TurnActivityProps) {
  const deepTutorUi = CHAT_DEEPTUTOR_TURN_UI_ENABLED;
  const toolCount = traceNodes.filter((node) => node.kind === "tool").length;
  const visible = activity.isRunning || traceNodes.length > 0 || thinkingBlocks.length > 0;
  const [open, setOpen] = useState<boolean | null>(null);
  const userToggledRef = useRef(false);
  const wasRunningRef = useRef(activity.isRunning);
  const wasComposingRef = useRef(activity.phase === "composing");
  const expanded = open ?? activity.isRunning;

  useEffect(() => {
    if (userToggledRef.current) return;
    const justStoppedRunning = wasRunningRef.current && !activity.isRunning;
    // DeepTutor-aligned timing: fold as soon as the turn enters the final
    // answer phase, not only once the whole Run reaches a terminal status.
    const enteringFinalAnswer = deepTutorUi && activity.phase === "composing" && !wasComposingRef.current;
    if (justStoppedRunning || enteringFinalAnswer) setOpen(false);
    wasRunningRef.current = activity.isRunning;
    wasComposingRef.current = activity.phase === "composing";
  }, [activity.isRunning, activity.phase, deepTutorUi]);

  // Hooks must run every render regardless of the `visible` early return below.
  const elapsedMs = useTurnElapsedSeconds(startedAt, deepTutorUi && activity.isRunning);

  if (!visible) return null;

  const hasThinking = thinkingBlocks.some((block) => {
    const value = blockValue(block);
    if (typeof value === "string") return Boolean(value.trim());
    const object = blockValueObject(block);
    return Object.values(object).some((item) => typeof item === "string" && item.trim());
  });
  // Tightened expandability (DeepTutor-aligned): don't show a chevron/expand
  // shell that opens onto nothing (e.g. running with no trace/thinking yet).
  const expandable = !deepTutorUi || traceNodes.length > 0 || hasThinking;
  const duration = activity.isTerminal ? formatTurnDuration(durationMs) : null;
  const liveDuration = elapsedMs != null ? formatTurnDuration(elapsedMs) : null;

  const toggle = () => {
    if (!expandable) return;
    userToggledRef.current = true;
    setOpen((value) => !(value ?? activity.isRunning));
  };

  const Mark = deepTutorUi ? markForPhase(activity.phase) : null;
  const bodyId = `turn-activity-body-${activityId ?? activity.runId ?? "turn"}`;
  // Pulse animation is part of the DeepTutor-aligned mark treatment only; the
  // legacy Sparkles icon keeps its pre-existing plain rendering unchanged.
  const markClassName = deepTutorUi && activity.isRunning ? "turn-activity__mark" : undefined;

  return <div className={`turn-activity${expanded ? " turn-activity--open" : ""}`}>
    <button
      type="button"
      className="turn-activity__header"
      aria-expanded={expandable ? expanded : undefined}
      aria-controls={expandable ? bodyId : undefined}
      onClick={toggle}
      disabled={!expandable}
    >
      <span className="turn-activity__state">
        {Mark ? <Mark size={16} className={markClassName} /> : <Sparkles size={22} aria-hidden="true" />}
      </span>
      <span className="turn-activity__label">{activity.publicStatusLabel}</span>
      {(duration ?? liveDuration) && <span className="turn-activity__duration">{duration ?? liveDuration}</span>}
      {toolCount > 0 && <span className="turn-activity__count"><Wrench size={11} aria-hidden="true" />{toolCount}</span>}
      {expandable && <ChevronDown size={15} className={`turn-activity__chevron${expanded ? " turn-activity__chevron--open" : ""}`} aria-hidden="true" />}
    </button>
    {expandable && <div id={bodyId} className={`turn-activity__body${expanded ? " turn-activity__body--open" : ""}`}>
      <div className="turn-activity__body-inner">
        {hasThinking && <div className="turn-activity__thinking">{thinkingBlocks.map((block) => <PublicThinkingCard block={block} key={block.id} />)}</div>}
        <TurnTrace nodes={traceNodes} />
      </div>
    </div>}
  </div>;
}
