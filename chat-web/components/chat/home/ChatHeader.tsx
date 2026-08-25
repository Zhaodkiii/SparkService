"use client";

import { useState } from "react";
import { BookmarkPlus, Check, Download, PanelRight, Pencil, X } from "lucide-react";
import { useOptionalThreads } from "@/context/ThreadContext";

function messageText(blocks: Array<{ payload: Record<string, unknown> }>) {
  return blocks.map((block) => typeof block.payload.text === "string" ? block.payload.text : "").filter(Boolean).join("\n\n");
}

export function ChatHeader({ activityOpen, onToggleActivity }: { activityOpen: boolean; onToggleActivity: () => void }) {
  const threads = useOptionalThreads();
  const thread = threads?.threads.find((item) => item.thread_id === threads.selectedThreadId);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const title = thread?.title || "新对话";
  const save = async () => {
    if (!thread || !draft.trim()) return;
    if (await threads?.renameThread(thread.thread_id, draft)) setEditing(false);
  };
  const download = () => {
    if (!threads?.messages.length) return;
    const body = threads.messages.map((message) => `## ${message.role === "user" ? "我" : message.role === "assistant" ? "小鲸 AI" : "系统"}\n\n${messageText(message.blocks)}`).join("\n\n---\n\n");
    const url = URL.createObjectURL(new Blob([`# ${title}\n\n${body}\n`], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${title.replace(/[\\/:*?\"<>|]/g, "-")}.md`; anchor.click(); URL.revokeObjectURL(url);
  };
  return <header className="chat-header">
    <div className="chat-header__title-wrap">
      {editing ? <form className="chat-title-edit" onSubmit={(event) => { event.preventDefault(); void save(); }}><input autoFocus value={draft} maxLength={120} aria-label="对话标题" onChange={(event) => setDraft(event.target.value)} /><button type="submit" aria-label="保存标题"><Check size={15} /></button><button type="button" aria-label="取消编辑" onClick={() => setEditing(false)}><X size={15} /></button></form> : <button className="chat-title" type="button" disabled={!thread} title={thread ? "重命名对话" : "开始对话后即可重命名"} onClick={() => { setDraft(title); setEditing(true); }}><span>{title}</span>{thread && <Pencil size={13} className="chat-title__pencil" />}</button>}
    </div>
    <div className="chat-header__actions">
      <button className="icon-button" type="button" disabled aria-label="保存到笔记本" title="保存到笔记本"><BookmarkPlus size={16} /></button>
      <button className="icon-button" type="button" disabled={!threads?.messages.length} aria-label="下载 Markdown" title="下载 Markdown" onClick={download}><Download size={16} /></button>
      <button className="icon-button" type="button" aria-label="活动" aria-pressed={activityOpen} title="会话活动、附件与预览" onClick={onToggleActivity}><PanelRight size={16} /></button>
    </div>
  </header>;
}
