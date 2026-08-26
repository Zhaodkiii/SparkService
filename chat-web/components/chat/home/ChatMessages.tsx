"use client";

import { HeartPulse, Sparkles } from "lucide-react";
import { AssistantTurn } from "@/components/chat/turn/AssistantTurn";
import { ChatBlockRenderer } from "@/components/chat/home/ChatBlockRenderer";
import { useChatRuntime } from "@/context/ChatRuntimeContext";
import { useOptionalRunControl } from "@/context/RunControlContext";
import { useOptionalThreads } from "@/context/ThreadContext";
import { runStatusLabel } from "@/lib/event-reducer";
import { toolBlockActivityView } from "@/lib/tools/tool-activity-selectors";
import type { ChatBlockDTO } from "@/types/chat";
import { blockAssociatedValue } from "@/lib/chat/block-normalizer";

/** 用户消息为紧凑气泡，正文直接以纯文本渲染，不套用 Markdown 卡片。 */
function userBubble(blocks: ChatBlockDTO[]) {
  const text = blocks.map((block) => {
    const value = blockAssociatedValue(block);
    return typeof value === "string" ? value : "";
  }).filter(Boolean).join("\n\n");
  return <article className="message message--user"><div className="message__content"><div className="message__body">{text}</div></div></article>;
}

function isStreaming(blocks: ChatBlockDTO[]): boolean {
  return blocks.some((block) => block.kind === "text" && block.status === "streaming");
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
    if (!threads.messages.length && !unsyncedLiveBlocks.length) return <div className="empty-state"><div className="empty-state__mark"><HeartPulse size={22} /></div><div><p className="empty-state__eyebrow">小鲸健康 AI</p><h1>今天想先聊点什么？</h1><p>可以从健康资料、饮食、运动或睡眠开始。</p><div className="prompt-suggestions"><span>解读体检指标</span><span>规划一周饮食</span><span>改善睡眠质量</span></div></div></div>;
    return <div className="messages" aria-live="polite">
      {threads.messages.map((message) => {
        const blocks = message.blocks.map((block) => live.state.blocksById[block.id] ?? block);
        if (message.role === "assistant") return <AssistantTurn key={message.client_message_id} blocks={blocks} messageId={message.client_message_id} turnSummary={message.turn_summary ?? null} usageSummary={message.usage_summary ?? null} />;
        return <div key={message.client_message_id}>{userBubble(blocks)}</div>;
      })}
      {(unsyncedLiveBlocks.length > 0 || Boolean(live.run && !["completed", "failed", "cancelled", "interrupted"].includes(live.run.status))) && <AssistantTurn
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
    {history.map((message) => <article className={`message message--${message.role}`} key={message.id}>{message.role === "assistant" && <div className="message__avatar" aria-hidden="true"><Sparkles size={14} /></div>}<div className="message__content"><div className="message__body">{message.attachment && <div className="attachment-card">附件：{message.attachment}</div>}{message.role === "user" ? message.text : blocks.length ? blocks.map((block) => <ChatBlockRenderer activity={activityFor(block)} block={block} key={block.id} />) : <p>{message.text}</p>}</div></div></article>)}
  </div>;
}
