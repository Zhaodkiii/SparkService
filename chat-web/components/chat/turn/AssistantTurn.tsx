"use client";

import { renderBlock } from "@/components/chat/blocks/registry";
import { TurnActivity } from "@/components/chat/turn/TurnActivity";
import { TurnActions } from "@/components/chat/turn/TurnActions";
import { TurnUsageSummary } from "@/components/chat/turn/TurnUsageSummary";
import { ToolPresentationSlot } from "@/components/chat/turn/ToolPresentationSlot";
import { buildTurnPresentation, collectToolActivityRows, normalizeUsage, turnVisibleText } from "@/lib/chat/turn-presentation";
import { projectTurnActivity } from "@/lib/chat/turn-activity-projector";
import { buildTurnTrace } from "@/lib/chat/turn-trace-reducer";
import type { AgentRoundTraceDTO, ChatBlockDTO, ChatRunDTO, ChatUsageSummary, TurnSummary } from "@/types/chat";
import type { ToolActivityDTO } from "@/types/tool";

function runDurationMs(run: ChatRunDTO | null | undefined): number | null {
  if (!run?.started_at || !run?.finished_at) return null;
  const start = Date.parse(run.started_at);
  const end = Date.parse(run.finished_at);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  return Math.max(0, end - start);
}

interface AssistantTurnProps {
  blocks: ChatBlockDTO[];
  messageId: string;
  activityByCallId?: (toolCallId: string | null | undefined) => ToolActivityDTO | null;
  run?: ChatRunDTO | null;
  assistantStatus?: string | null;
  contentStreaming?: boolean;
  turnSummary?: TurnSummary | null;
  usageSummary?: ChatUsageSummary | null;
  rounds?: Record<string, AgentRoundTraceDTO> | null;
  onRegenerate?: () => void;
  onDelete?: () => void;
  onFeedback?: (value: "up" | "down") => void;
}

/** 统一助手回合外壳：Activity 状态头是唯一入口，不再渲染固定头像。 */
export function AssistantTurn({ blocks, messageId, activityByCallId, run, assistantStatus, contentStreaming, turnSummary, usageSummary, rounds, onRegenerate, onDelete, onFeedback }: AssistantTurnProps) {
  const presentation = buildTurnPresentation(blocks, messageId, "assistant");
  const toolRows = collectToolActivityRows(blocks, activityByCallId);
  const traceNodes = buildTurnTrace(rounds ?? null, toolRows);
  const activity = projectTurnActivity({
    runId: run?.id ?? turnSummary?.run_id ?? null,
    runStatus: run?.status ?? turnSummary?.status ?? null,
    assistantStatus: assistantStatus ?? null,
    toolRows,
    contentStreaming: Boolean(contentStreaming),
  });
  const text = turnVisibleText(blocks);
  const usage = normalizeUsage(usageSummary, turnSummary?.usage);
  const durationMs = turnSummary?.duration_ms ?? runDurationMs(run);
  const startedAt = run?.started_at ?? turnSummary?.started_at ?? null;

  return <article className="message message--assistant">
    <div className="message__content">
      <div className="message__body">
        <TurnActivity activity={activity} thinkingBlocks={presentation.thinkingBlocks} traceNodes={traceNodes} durationMs={durationMs} startedAt={startedAt} activityId={messageId} />
        {presentation.contentBlocks.map((block) => <div key={block.id}>{renderBlock({ block })}</div>)}
        <ToolPresentationSlot blocks={presentation.presentationBlocks} />
      </div>
      <TurnActions text={text} onRegenerate={onRegenerate} onDelete={onDelete} onFeedback={onFeedback} />
      <TurnUsageSummary usage={usage} />
    </div>
  </article>;
}
