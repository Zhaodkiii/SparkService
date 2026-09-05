"use client";

import { HeartPulse } from "lucide-react";
import { AssistantTurn } from "@/components/chat/turn/AssistantTurn";
import { ChatBlockRenderer } from "@/components/chat/home/ChatBlockRenderer";
import { useChatRuntime } from "@/context/ChatRuntimeContext";
import { useOptionalRunControl } from "@/context/RunControlContext";
import { useOptionalThreads } from "@/context/ThreadContext";
import { runStatusLabel } from "@/lib/event-reducer";
import { toolBlockActivityView } from "@/lib/tools/tool-activity-selectors";
import { UserMessageContent } from "@/components/chat/home/UserMessageBubble";
import type { ChatBlockDTO, ChatRunDTO } from "@/types/chat";
import { isTerminalRunStatus } from "@/types/chat";
import type { ChatMessageWireDTO } from "@/types/sync";

/**
 * 用户消息为紧凑气泡：内容渲染与医生工作台患者消息共用 UserMessageContent。
 */
function userBubble(blocks: ChatBlockDTO[]) {
  return <article className="message message--user"><div className="message__content">
    <UserMessageContent blocks={blocks} />
  </div></article>;
}

function isStreaming(blocks: ChatBlockDTO[]): boolean {
  return blocks.some((block) => block.kind === "text" && block.status === "streaming");
}

function belongsToLiveRun(message: ChatMessageWireDTO, run: ChatRunDTO | null | undefined, liveBlockIds: Set<string>, lastAssistantId: string | null): boolean {
  if (!run || isTerminalRunStatus(run.status) || message.role !== "assistant") return false;
  if (message.turn_summary?.run_id === run.id) return true;
  if (message.blocks.some((block) => liveBlockIds.has(block.id))) return true;
  return message.client_message_id === lastAssistantId && message.blocks.length === 0;
}

export function ChatMessages() {
  const { state, history, scenario, offline, forbidden } = useChatRuntime();
  const live = useOptionalRunControl();
  const threads = useOptionalThreads();
  const liveRunId = live?.run?.id ?? null;
  const activityFor = (block: ChatBlockDTO) => toolBlockActivityView(live?.state ?? null, liveRunId, block);
  const activityByCallId = (toolCallId: string | null | undefined) => (liveRunId && toolCallId ? live?.state.toolCallsByRun[liveRunId]?.[toolCallId] ?? null : null);
  if (live && threads) {
    const liveBlocks = Object.values(live.state.blocksById);
    const syncedBlockIds = new Set(threads.messages.flatMap((message) => message.blocks.map((block) => block.id)));
    const unsyncedLiveBlocks = liveBlocks.filter((block) => !syncedBlockIds.has(block.id));
    const liveBlockIds = new Set(liveBlocks.map((block) => block.id));
    const lastAssistantId = [...threads.messages].reverse().find((message) => message.role === "assistant")?.client_message_id ?? null;
    const liveClaimed = Boolean(live.run && threads.messages.some((message) => belongsToLiveRun(message, live.run, liveBlockIds, lastAssistantId)));
    const liveActive = Boolean(live.run && !isTerminalRunStatus(live.run.status));
    if (!threads.messages.length && !unsyncedLiveBlocks.length) return <div className="empty-state"><div className="empty-state__mark"><HeartPulse size={22} /></div><div><p className="empty-state__eyebrow">小鲸健康 AI</p><h1>今天想先聊点什么？</h1><p>可以从健康资料、饮食、运动或睡眠开始。</p><div className="prompt-suggestions"><span>解读体检指标</span><span>规划一周饮食</span><span>改善睡眠质量</span></div></div></div>;
    return <div className="messages" aria-live="polite">
      {threads.messages.map((message) => {
        const onLiveRun = belongsToLiveRun(message, live.run, liveBlockIds, lastAssistantId);
        const extraLiveBlocks = onLiveRun ? unsyncedLiveBlocks : [];
        const blocks = [
          ...message.blocks.map((block) => live.state.blocksById[block.id] ?? block),
          ...extraLiveBlocks,
        ];
        if (message.role === "assistant") {
          return <AssistantTurn
            key={message.client_message_id}
            blocks={blocks}
            messageId={message.client_message_id}
            turnSummary={message.turn_summary ?? null}
            usageSummary={message.usage_summary ?? null}
            activityByCallId={onLiveRun ? activityByCallId : undefined}
            run={onLiveRun ? live.run : null}
            assistantStatus={onLiveRun && liveRunId ? live.state.assistantStatusByRun[liveRunId] ?? null : null}
            contentStreaming={onLiveRun ? isStreaming(blocks) : false}
            rounds={onLiveRun && liveRunId ? live.state.roundsByRun[liveRunId] ?? null : null}
          />;
        }
        return <div key={message.client_message_id}>{userBubble(blocks)}</div>;
      })}
      {((unsyncedLiveBlocks.length > 0 || liveActive) && !liveClaimed) && <AssistantTurn
        key={`live-${liveRunId ?? "assistant"}`}
        blocks={unsyncedLiveBlocks}
        messageId={`live-${liveRunId ?? "assistant"}`}
        activityByCallId={activityByCallId}
        run={live.run}
        assistantStatus={liveRunId ? live.state.assistantStatusByRun[liveRunId] ?? null : null}
        contentStreaming={isStreaming(unsyncedLiveBlocks)}
        rounds={liveRunId ? live.state.roundsByRun[liveRunId] ?? null : null}
      />}
      {live.run && ["failed", "interrupted"].includes(live.run.status) && <div className="run-error" role="alert"><span>{live.run.error?.message || runStatusLabel(live.run.status)}</span><button type="button" onClick={() => void live.regenerate()} disabled={live.busy}>重新生成</button></div>}
    </div>;
  }
  if (forbidden) return <div className="empty-state" role="alert"><div><h1>需要重新确认账号</h1><p>为了保护隐私，没有显示上一账号的内容。</p></div></div>;
  if (scenario === "empty") return <div className="empty-state"><div className="empty-state__mark"><HeartPulse size={22} /></div><div><h1>今天想先聊点什么？</h1><p>可以从健康资料、饮食或睡眠开始。</p></div></div>;
  const blocks = Object.values(state.blocksById);
  return <div className="messages" aria-live="polite">
    {offline && <div className="run-banner" role="status">当前离线，只能查看已同步历史</div>}
    {history.map((message) => <article className={`message message--${message.role}`} key={message.id}><div className="message__content"><div className="message__body">{message.attachment && <div className="attachment-card">附件：{message.attachment}</div>}{message.role === "user" ? message.text : blocks.length ? blocks.map((block) => <ChatBlockRenderer activity={activityFor(block)} block={block} key={block.id} />) : <p>{message.text}</p>}</div></div></article>)}
  </div>;
}
