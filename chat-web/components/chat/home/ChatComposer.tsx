"use client";

import { ArrowUp, Image as ImageIcon, MessageCircle, Mic, Square } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { ComposerInput } from "@/components/chat/home/ComposerInput";
import { ComposerImageStrip } from "@/components/chat/home/ComposerImageStrip";
import { ContextToolbar } from "@/components/chat/context/ContextToolbar";
import { useOptionalAuth } from "@/context/AuthContext";
import { useOptionalChatContext } from "@/context/ChatContextProvider";
import { useOptionalRunControl } from "@/context/RunControlContext";
import { useOptionalThreads } from "@/context/ThreadContext";
import { SparkChatImageApi } from "@/lib/api/chat-image-api";
import { useImageDrafts } from "@/lib/chat/use-image-drafts";

export function ChatComposer() {
  const [value, setValue] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [imageHint, setImageHint] = useState<string | null>(null);
  const auth = useOptionalAuth();
  const runControl = useOptionalRunControl();
  const threads = useOptionalThreads();
  const context = useOptionalChatContext();
  const running = Boolean(runControl?.run && !["completed", "failed", "cancelled", "interrupted"].includes(runControl.run.status));

  // CHAT-WEB-029：图片草稿（选择 → 压缩 → 直传 OSS → 登记 → ready）。
  const supportsImageInput = runControl?.supportsImageInput ?? false;
  const imageApi = useMemo(() => (auth ? new SparkChatImageApi(auth.client) : null), [auth]);
  const imageDrafts = useImageDrafts({ api: imageApi, threadId: threads?.selectedThreadId ?? null, supportsImageInput });
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  // 含图消息的稳定 client_message_id：首次发送生成，重试复用，成功后清空。
  const clientMessageIdRef = useRef<string | null>(null);

  const pickImages = () => {
    if (!supportsImageInput) { setImageHint("当前模型不支持图片理解"); return; }
    fileInputRef.current?.click();
  };
  const onFilesSelected = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length) return;
    const result = imageDrafts.selectImages(files);
    if (result.errorCode === "chat_image_capability_unavailable") setImageHint("当前模型不支持图片理解");
    else if (result.errorCode === "chat_image_count_exceeded") setImageHint(`最多发送 ${imageDrafts.maxDrafts} 张图片`);
    else setImageHint(null);
  };

  const submit = async () => {
    if (running) return;
    if (imageDrafts.hasPending) { setImageHint("图片尚未上传完成"); return; }
    if (!value.trim() && !imageDrafts.allReady) return;
    if (!runControl) { setSubmitted(true); return; }
    const threadId = threads ? await threads.materializeDraftThread() : null;
    if (!threadId) return;
    setImageHint(null);
    const images = imageDrafts.readyImages;
    let clientMessageId: string | undefined;
    if (images.length) {
      clientMessageIdRef.current ??= crypto.randomUUID();
      clientMessageId = clientMessageIdRef.current;
    }
    imageDrafts.markSending();
    const accepted = await runControl.createRun(value, context?.createTurnContext(), threadId, { images, clientMessageId });
    if (accepted) {
      context?.clearDraft();
      setValue("");
      imageDrafts.clear();
      clientMessageIdRef.current = null;
    } else {
      // CreateRun 失败：保留文本与图片草稿（fileId 不丢），可复用 client_message_id 重试。
      imageDrafts.resetForRetry();
    }
  };

  const sendDisabled = (!value.trim() && !imageDrafts.allReady) || imageDrafts.hasPending || Boolean(runControl?.busy) || context?.status === "loading" || context?.status === "saving";
  const statusText = imageHint
    ?? (imageDrafts.hasPending ? "图片尚未上传完成" : null)
    ?? (threads?.error ? `${threads.error}，请刷新后重试` : null)
    ?? runControl?.error
    ?? (submitted ? "消息已准备好，网络发送将在 P1 接入" : null)
    ?? "小鲸健康 AI 可能会出错，重要医疗决定请咨询专业医生";

  return <div className="composer-shell">
    <div className="composer" aria-label="消息编辑器">
      <ComposerImageStrip drafts={imageDrafts.drafts} onRetry={imageDrafts.retry} onRemove={imageDrafts.remove} />
      <ComposerInput value={value} onChange={(next) => { setValue(next); setSubmitted(false); }} onSubmit={() => void submit()} disabled={Boolean(runControl?.busy)} />
      <div className="composer__footer">
        <div className="composer__tools">
          <button className="composer-mode" type="button" aria-label="当前模式：聊天"><MessageCircle size={14} /><span>聊天</span></button>
          <ContextToolbar />
          <button
            className="composer-icon"
            type="button"
            aria-label="添加图片"
            aria-disabled={!supportsImageInput}
            title={supportsImageInput ? "添加图片" : "当前模型不支持图片理解"}
            onClick={pickImages}
          ><ImageIcon size={17} /></button>
          <input ref={fileInputRef} type="file" accept="image/*" multiple hidden aria-hidden="true" tabIndex={-1} onChange={onFilesSelected} />
        </div>
        <div className="composer__actions"><button className="composer-icon" type="button" aria-label="语音输入" title="语音输入即将开放" disabled><Mic size={17} /></button>{running ? <button className="send-button send-button--stop" type="button" aria-label="停止生成" onClick={() => void runControl?.cancelRun()} disabled={runControl?.busy}><Square size={12} fill="currentColor" /></button> : <button className="send-button" type="button" aria-label="发送" onClick={() => void submit()} disabled={sendDisabled}><ArrowUp size={18} strokeWidth={2.2} /></button>}</div>
      </div>
    </div>
    <div className="composer-status" aria-live="polite">{statusText}</div>
  </div>;
}
