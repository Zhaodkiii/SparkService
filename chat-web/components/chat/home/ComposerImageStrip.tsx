"use client";

import { X } from "lucide-react";
import type { ImageDraft } from "@/lib/chat/image-drafts";

/** 草稿状态对应的中文文案。 */
function statusCopy(draft: ImageDraft): string {
  switch (draft.status) {
    case "selected":
    case "processing":
      return "处理中…";
    case "ready_to_upload":
      return "等待上传…";
    case "uploading":
      return `正在上传 ${draft.progress}%`;
    case "uploaded":
    case "registering":
      return "登记中…";
    case "ready":
      return "上传完成";
    case "sending":
      return "发送中…";
    case "sent":
      return "已发送";
    case "failed":
      return "上传失败";
    default:
      return "";
  }
}

/**
 * 输入区图片预览条（CHAT-WEB-029）：缩略图、文件名、状态文案、上传进度，
 * 失败时提供重试/移除，每张卡右上角 × 移除。
 */
export function ComposerImageStrip({ drafts, onRetry, onRemove }: {
  drafts: ImageDraft[];
  onRetry: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  if (!drafts.length) return null;
  return <div className="composer-images" role="list" aria-label="待发送图片">
    {drafts.map((draft) => <div className="composer-image-card" role="listitem" key={draft.id}>
      <span className="composer-image-card__thumb"><img src={draft.previewUrl} alt={draft.fileName} /></span>
      <span className="composer-image-card__meta">
        <span className="composer-image-card__name" title={draft.fileName}>{draft.fileName}</span>
        <span className={draft.status === "failed" ? "composer-image-card__status composer-image-card__status--failed" : "composer-image-card__status"}>{statusCopy(draft)}</span>
        {draft.status === "uploading" ? <span className="composer-image-card__progress"><i style={{ width: `${draft.progress}%` }} /></span> : null}
        {draft.status === "failed" ? <span className="composer-image-card__actions">
          {draft.error?.retryable !== false ? <button type="button" onClick={() => onRetry(draft.id)}>重试</button> : null}
          <button type="button" onClick={() => onRemove(draft.id)}>移除</button>
        </span> : null}
      </span>
      <button className="composer-image-card__remove" type="button" aria-label={`移除图片 ${draft.fileName}`} onClick={() => onRemove(draft.id)}><X size={11} /></button>
    </div>)}
  </div>;
}
