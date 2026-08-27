"use client";

import { useState } from "react";
import { BookmarkPlus, Check, Download, PanelRight, Pencil, X } from "lucide-react";
import { useOptionalThreads } from "@/context/ThreadContext";
import { blockAssociatedValue } from "@/lib/chat/block-normalizer";
import { sortChatMessagesForDisplay } from "@/lib/chat/message-order";

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
    const messages = threads.messages;
    const userMessages = messages.filter((message) => message.role === "user").length;
    const assistantMessages = messages.filter((message) => message.role === "assistant").length;
    const modelName = thread?.current_model_name?.trim();
    const selectedModel = modelName ? modelName : "未设置";
    const summary = [
      "ChatView 对话调试信息:",
      `- ThreadID: ${threads.selectedThreadId ?? ""}`,
      `- 标题: ${title}`,
      `- 选择模型: ${selectedModel}`,
      `- 消息总数: ${messages.length} (用户: ${userMessages}, 助手: ${assistantMessages})`,
      `- 参数: temperature=${thread?.temperature ?? 0}, topP=${thread?.top_p ?? 0}, maxTokens=${thread?.max_tokens ?? 0}, maxMessages=${thread?.max_messages ?? 0}`,
      `- 图片送达方式(本会话): ${thread?.image_delivery_mode ?? "-"}`,
    ].join("\n");

    const rows = sortChatMessagesForDisplay(messages)
      .map((message) => {
        const attachments = message.blocks
          .filter((block) => block.kind === "imageGallery" || block.kind === "fileAttachments")
          .flatMap((block) => {
            const items = block.payload.images ?? block.payload.items ?? block.payload.files ?? block.payload.attachments;
            return Array.isArray(items) ? items : [];
          });
        const contentPreview = message.blocks
          .map((block) => {
            const value = blockAssociatedValue(block);
            return typeof value === "string" ? value : "";
          })
          .filter(Boolean)
          .join("\n")
          .slice(0, 300);
        const row: Record<string, unknown> = {
          id: message.server_message_id ?? message.client_message_id,
          client_message_id: message.client_message_id,
          role: message.role,
          delivery_state: message.delivery_state,
          created_at: message.created_at,
          content_preview: contentPreview,
          attachments_count: attachments.length,
          blocks_count: message.blocks.length,
        };
        if (attachments.length) row.attachments = attachments;
        row.blocks = message.blocks;
        if (message.reasoning_content) row.reasoning_preview = message.reasoning_content.slice(-200);
        if (message.model_name) row.model_name = message.model_name;
        return row;
      });

    const exportData = {
      thread_id: thread?.thread_id ?? threads.selectedThreadId ?? "",
      title: thread?.title ?? "",
      debug_time: new Date().toISOString(),
      summary,
      messages: rows,
    };

    const json = JSON.stringify(exportData, null, 2);
    const url = URL.createObjectURL(new Blob([json], { type: "application/json;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${title.replace(/[\\/:*?\"<>|]/g, "-")}.json`; anchor.click(); URL.revokeObjectURL(url);
  };
  return <header className="chat-header">
    <div className="chat-header__title-wrap">
      {editing ? <form className="chat-title-edit" onSubmit={(event) => { event.preventDefault(); void save(); }}><input autoFocus value={draft} maxLength={120} aria-label="对话标题" onChange={(event) => setDraft(event.target.value)} /><button type="submit" aria-label="保存标题"><Check size={15} /></button><button type="button" aria-label="取消编辑" onClick={() => setEditing(false)}><X size={15} /></button></form> : <button className="chat-title" type="button" disabled={!thread} title={thread ? "重命名对话" : "开始对话后即可重命名"} onClick={() => { setDraft(title); setEditing(true); }}><span>{title}</span>{thread && <Pencil size={13} className="chat-title__pencil" />}</button>}
    </div>
    <div className="chat-header__actions">
      <button className="icon-button" type="button" disabled aria-label="保存到笔记本" title="保存到笔记本"><BookmarkPlus size={16} /></button>
      <button className="icon-button" type="button" disabled={!threads?.messages.length} aria-label="下载对话记录" title="下载对话记录" onClick={download}><Download size={16} /></button>
      <button className="icon-button" type="button" aria-label="活动" aria-pressed={activityOpen} title="会话活动、附件与预览" onClick={onToggleActivity}><PanelRight size={16} /></button>
    </div>
  </header>;
}
