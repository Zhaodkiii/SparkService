"use client";

import { Check, Clipboard, HeartPulse, RefreshCcw, Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { ChatBlockRenderer } from "@/components/chat/home/ChatBlockRenderer";
import { useChatRuntime } from "@/context/ChatRuntimeContext";
import { useOptionalRunControl } from "@/context/RunControlContext";
import { useOptionalThreads } from "@/context/ThreadContext";
import { runStatusLabel } from "@/lib/event-reducer";
import type { ChatBlockDTO } from "@/types/chat";

function blocksText(blocks: ChatBlockDTO[]) { return blocks.map((block) => typeof block.payload.text === "string" ? block.payload.text : "").filter(Boolean).join("\n\n"); }

function MessageActions({ blocks, onRegenerate }: { blocks: ChatBlockDTO[]; onRegenerate?: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => { await navigator.clipboard.writeText(blocksText(blocks)); setCopied(true); window.setTimeout(() => setCopied(false), 1600); };
  return <div className="message-actions">
    <button type="button" aria-label="复制回答" title="复制回答" disabled={!blocksText(blocks)} onClick={() => void copy()}>{copied ? <Check size={14} /> : <Clipboard size={14} />}</button>
    <button type="button" aria-label="有帮助" title="有帮助"><ThumbsUp size={14} /></button><button type="button" aria-label="没有帮助" title="没有帮助"><ThumbsDown size={14} /></button>
    {onRegenerate && <button type="button" aria-label="重新生成" title="重新生成" onClick={onRegenerate}><RefreshCcw size={14} /></button>}
  </div>;
}

export function ChatMessages() {
  const { state, history, scenario, offline, forbidden } = useChatRuntime();
  const live = useOptionalRunControl();
  const threads = useOptionalThreads();
  if (live && threads) {
    const liveBlocks = Object.values(live.state.blocksById);
    const syncedBlockIds = new Set(threads.messages.flatMap((message) => message.blocks.map((block) => block.id)));
    const unsyncedLiveBlocks = liveBlocks.filter((block) => !syncedBlockIds.has(block.id));
    if (!threads.messages.length && !unsyncedLiveBlocks.length) return <div className="empty-state"><div className="empty-state__mark"><HeartPulse size={22} /></div><div><p className="empty-state__eyebrow">小鲸健康 AI</p><h1>今天想先聊点什么？</h1><p>可以从健康资料、饮食、运动或睡眠开始。</p><div className="prompt-suggestions"><span>解读体检指标</span><span>规划一周饮食</span><span>改善睡眠质量</span></div></div></div>;
    return <div className="messages" aria-live="polite">
      {threads.messages.map((message) => <article className={`message message--${message.role}`} key={message.client_message_id}>
        {message.role === "assistant" && <div className="message__avatar" aria-hidden="true"><Sparkles size={14} /></div>}
        <div className="message__content"><div className="message__body">{message.blocks.map((block) => <ChatBlockRenderer block={live.state.blocksById[block.id] ?? block} key={block.id} />)}</div>{message.role === "assistant" && <MessageActions blocks={message.blocks.map((block) => live.state.blocksById[block.id] ?? block)} />}</div>
      </article>)}
      {unsyncedLiveBlocks.length > 0 && <article className="message message--assistant"><div className="message__avatar" aria-hidden="true"><Sparkles size={14} /></div><div className="message__content"><div className="message__body">{unsyncedLiveBlocks.map((block) => <ChatBlockRenderer block={block} key={block.id} />)}</div><MessageActions blocks={unsyncedLiveBlocks} /></div></article>}
      {live.run && !["completed", "failed", "cancelled", "interrupted"].includes(live.run.status) && <div className="generation-status" role="status"><span className="generation-status__pulse" />{runStatusLabel(live.run.status)}</div>}
      {live.run && ["failed", "interrupted"].includes(live.run.status) && <div className="run-error" role="alert"><span>{live.run.error?.message || runStatusLabel(live.run.status)}</span><button type="button" onClick={() => void live.regenerate()} disabled={live.busy}>重新生成</button></div>}
    </div>;
  }
  if (forbidden) return <div className="empty-state" role="alert"><div><h1>需要重新确认账号</h1><p>为了保护隐私，没有显示上一账号的内容。</p></div></div>;
  if (scenario === "empty") return <div className="empty-state"><div className="empty-state__mark"><HeartPulse size={22} /></div><div><h1>今天想先聊点什么？</h1><p>可以从健康资料、饮食或睡眠开始。</p></div></div>;
  const blocks = Object.values(state.blocksById);
  return <div className="messages" aria-live="polite">
    {offline && <div className="run-banner" role="status">当前离线，只能查看已同步历史</div>}
    {history.map((message) => <article className={`message message--${message.role}`} key={message.id}>{message.role === "assistant" && <div className="message__avatar"><Sparkles size={14} /></div>}<div className="message__content"><div className="message__body">{message.attachment && <div className="attachment-card">附件：{message.attachment}</div>}{message.role === "user" ? message.text : blocks.length ? blocks.map((block) => <ChatBlockRenderer block={block} key={block.id} />) : <p>{message.text}</p>}</div>{message.role === "assistant" && <MessageActions blocks={blocks} />}</div></article>)}
  </div>;
}
