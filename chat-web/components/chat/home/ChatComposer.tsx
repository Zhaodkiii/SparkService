"use client";

import { ArrowUp, MessageCircle, Mic, Square } from "lucide-react";
import { useState } from "react";
import { ComposerInput } from "@/components/chat/home/ComposerInput";
import { ContextToolbar } from "@/components/chat/context/ContextToolbar";
import { useOptionalChatContext } from "@/context/ChatContextProvider";
import { useOptionalRunControl } from "@/context/RunControlContext";
import { useOptionalThreads } from "@/context/ThreadContext";

export function ChatComposer() {
  const [value, setValue] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const runControl = useOptionalRunControl();
  const threads = useOptionalThreads();
  const context = useOptionalChatContext();
  const running = Boolean(runControl?.run && !["completed", "failed", "cancelled", "interrupted"].includes(runControl.run.status));
  const submit = async () => {
    if (!value.trim() || running) return;
    if (!runControl) { setSubmitted(true); return; }
    const threadId = threads ? await threads.materializeDraftThread() : null;
    if (!threadId) return;
    const accepted = await runControl.createRun(value, context?.createTurnContext(), threadId);
    if (accepted) { context?.clearDraft(); setValue(""); }
  };
  return <div className="composer-shell">
    <div className="composer" aria-label="消息编辑器">
      <ComposerInput value={value} onChange={(next) => { setValue(next); setSubmitted(false); }} onSubmit={() => void submit()} disabled={Boolean(runControl?.busy)} />
      <div className="composer__footer">
        <div className="composer__tools"><button className="composer-mode" type="button" aria-label="当前模式：聊天"><MessageCircle size={14} /><span>聊天</span></button><ContextToolbar /></div>
        <div className="composer__actions"><button className="composer-icon" type="button" aria-label="语音输入" title="语音输入即将开放" disabled><Mic size={17} /></button>{running ? <button className="send-button send-button--stop" type="button" aria-label="停止生成" onClick={() => void runControl?.cancelRun()} disabled={runControl?.busy}><Square size={12} fill="currentColor" /></button> : <button className="send-button" type="button" aria-label="发送" onClick={() => void submit()} disabled={!value.trim() || Boolean(runControl?.busy) || context?.status === "loading" || context?.status === "saving"}><ArrowUp size={18} strokeWidth={2.2} /></button>}</div>
      </div>
    </div>
    <div className="composer-status" aria-live="polite">{threads?.error ? `${threads.error}，请刷新后重试` : runControl?.error ? runControl.error : submitted ? "消息已准备好，网络发送将在 P1 接入" : "小鲸健康 AI 可能会出错，重要医疗决定请咨询专业医生"}</div>
  </div>;
}
