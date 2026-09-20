"use client";

import { useState } from "react";
import { Check, CheckCircle2, Download, Eye, FileText, Image as ImageIcon, Paperclip, UploadCloud } from "lucide-react";
import { asRecord, asString, BlockShell, blockValue, blockValueObject, ReadOnlyCard } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";
import { useOptionalAttachmentPreview } from "@/components/shared/AttachmentPreviewProvider";

function asList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

interface GalleryImage {
  url: string;
  caption: string | null;
  filename: string | null;
}

/**
 * 单张图片（CHAT-WEB-029）：加载失败时替换为固定尺寸占位卡，
 * “重试加载”只重置该图 src（追加 retry 参数 bust 缓存），不影响其他图片。
 */
export function GalleryImageView({ image, index, total }: { image: GalleryImage; index: number; total: number }) {
  const preview = useOptionalAttachmentPreview();
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const openPreview = () => {
    if (!image.url || !preview) return;
    preview.open({
      url: image.url,
      filename: image.filename ?? image.caption ?? `图片 ${index + 1}`,
      kind: "image",
    });
  };
  if (failed) {
    return <figure className="gallery-item gallery-item--failed" role="status">
      <ImageIcon size={18} aria-hidden="true" />
      <strong>图片加载失败</strong>
      <span className="gallery-item__label">{image.filename ?? image.caption ?? `共 ${total} 张图片`}</span>
      <button type="button" onClick={() => { setAttempt((count) => count + 1); setFailed(false); }}>重试加载</button>
    </figure>;
  }
  const src = attempt > 0 ? `${image.url}${image.url.includes("?") ? "&" : "?"}retry=${attempt}` : image.url;
  return <figure className="gallery-item gallery-item--previewable" role="button" tabIndex={0} onClick={openPreview} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openPreview(); } }}>
    <img src={src} alt={image.caption ?? image.filename ?? `图片 ${index + 1}`} loading="lazy" onError={() => setFailed(true)} />
    {image.caption ? <figcaption>{image.caption}</figcaption> : null}
  </figure>;
}

export function ImageGalleryBlock({ block }: BlockRenderProps) {
  // 兼容两种 _0 形态：iOS 直接是图片数组；Web/工单形状为 {"images": [...]}。
  const value = blockValue(block);
  const list = Array.isArray(value) ? value : (asRecord(value).images ?? asRecord(value).items);
  const images = asList(list).map((item) => ({
    url: asString(item.url ?? item.src) ?? "",
    caption: asString(item.caption ?? item.alt ?? item.title),
    filename: asString(item.filename ?? item.name),
  }));
  const valid = images.filter((image) => image.url);
  return <BlockShell block={block}><ReadOnlyCard title="图片">
    {valid.length === 0 ? null : <div className="block block--gallery" role="list">{valid.map((image, index) => <GalleryImageView key={index} image={image} index={index} total={valid.length} />)}</div>}
  </ReadOnlyCard></BlockShell>;
}

export function FileAttachmentsBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const files = asList(value.files ?? value.attachments).map((item) => ({ name: asString(item.name ?? item.title ?? item.filename) ?? "附件", url: asString(item.url ?? item.href), size: asString(item.size) }));
  return <BlockShell block={block}><ReadOnlyCard title="附件">
    {files.length === 0 ? null : <ul className="block block--files" role="list">{files.map((file, index) => <li key={index}><Paperclip size={14} /><span>{file.name}</span>{file.size && <em>{file.size}</em>}{file.url && <a href={file.url} target="_blank" rel="noreferrer noopener" aria-label={`下载 ${file.name}`}><Download size={14} /></a>}</li>)}</ul>}
  </ReadOnlyCard></BlockShell>;
}

function formatAttachmentSize(value: unknown): string | null {
  const bytes = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** DOCTOR-WORKSPACE-000004：问诊文档附件（PDF 等医疗文件）画廊块。
 *  payload 形态与 imageGallery 对齐：{"file_gallery": {"_0": [...]}}。 */
export function FileGalleryBlock({ block }: BlockRenderProps) {
  const preview = useOptionalAttachmentPreview();
  const value = blockValue(block);
  const list = Array.isArray(value) ? value : (asRecord(value).files ?? asRecord(value).items ?? Object.values(asRecord(value)).find(Array.isArray));
  const files = asList(list).map((item) => ({
    name: asString(item.filename ?? item.name ?? item.title) ?? "问诊附件",
    url: asString(item.url ?? item.href),
    size: formatAttachmentSize(item.file_size ?? item.size),
    mime: asString(item.mime_type),
  }));
  return <BlockShell block={block}><ReadOnlyCard title="问诊附件">
    {files.length === 0 ? null : <ul className="block block--files" role="list">{files.map((file, index) => <li key={index}>
      <button
        type="button"
        className="block--files__preview"
        disabled={!file.url || !preview}
        onClick={() => {
          if (!file.url || !preview) return;
          preview.open({ url: file.url, filename: file.name, mime_type: file.mime, kind: file.mime?.startsWith("image/") ? "image" : "document" });
        }}
      >
        <Paperclip size={14} /><span>{file.name}</span>{file.size && <em>{file.size}</em>}
      </button>
      {file.url && <a href={file.url} target="_blank" rel="noreferrer noopener" aria-label={`下载 ${file.name}`} onClick={(event) => event.stopPropagation()}><Download size={14} /></a>}
    </li>)}</ul>}
  </ReadOnlyCard></BlockShell>;
}

export function CaptureCardBlock({ block }: BlockRenderProps) {
  const preview = useOptionalAttachmentPreview();
  const [viewed, setViewed] = useState(false);
  const value = blockValueObject(block);
  const cardType = asString(value.card_type ?? value.cardType);
  if (cardType === "supplementary_report") {
    const status = asString(value.status) ?? "pending";
    const attachments = asList(value.selected_attachments ?? value.selectedAttachments).map((item, index) => ({
      id: asString(item.id) ?? `attachment-${index}`,
      name: asString(item.display_name ?? item.displayName ?? item.filename ?? item.name) ?? "补充报告",
      url: asString(item.preview_url ?? item.previewURL ?? item.public_url ?? item.publicURL ?? item.url),
      mime: asString(item.mime_type ?? item.mimeType),
      kind: asString(item.kind),
      size: formatAttachmentSize(item.byte_count ?? item.byteCount ?? item.file_size),
    }));
    const isCompleted = status === "completed";
    // 患者端上传完成后一次性回写原卡片；医生端不展示中间上传态。
    // 历史数据若短暂带有 uploading/processing，仍按待上传占位，避免出现
    // 一个无法操作的“上传中”状态。
    const state = isCompleted ? (viewed ? "viewed" : "complete") : status === "failed" ? "failed" : "waiting";
    const stateLabel = state === "viewed" ? "已查看" : state === "complete" ? "已收到" : state === "failed" ? "上传失败" : "待上传";
    const stateDescription = state === "viewed"
      ? "报告已打开，可再次点击附件查看。"
      : state === "complete"
        ? "患者已补充报告，点击缩略图即可预览原文件。"
        : state === "failed"
            ? "患者上传报告失败，等待重新上传。"
            : "已向患者发送报告上传卡，等待患者补充。";
    const images = attachments.filter((item) => item.kind === "image" || item.mime?.startsWith("image/"));
    const files = attachments.filter((item) => !images.includes(item));
    const openAttachment = (file: typeof attachments[number]) => {
      if (!file.url || !preview) return;
      setViewed(true);
      preview.open({
        url: file.url,
        filename: file.name,
        mime_type: file.mime,
        kind: file.kind === "image" || file.mime?.startsWith("image/") ? "image" : "document",
      });
    };
    return <BlockShell block={block}>
      <article className={`supplementary-report-card supplementary-report-card--${state}`} aria-label="补充报告">
        <header className="supplementary-report-card__header">
          <div className="supplementary-report-card__icon" aria-hidden="true">
            {state === "waiting" ? <UploadCloud size={18} /> : state === "failed" ? <UploadCloud size={18} /> : <CheckCircle2 size={18} />}
          </div>
          <div className="supplementary-report-card__heading">
            <div className="supplementary-report-card__title-row">
              <h3>补充报告</h3>
              <span className="supplementary-report-card__status">{stateLabel}</span>
            </div>
            <p>{stateDescription}</p>
          </div>
        </header>

        {state === "waiting" ? (
          <div className="supplementary-report-card__empty">
            <div className="supplementary-report-card__empty-icon"><FileText size={22} /></div>
            <strong>等待患者上传检查报告</strong>
            <span>患者上传后，报告会显示在当前卡片内。</span>
          </div>
        ) : null}

        {isCompleted && attachments.length > 0 ? (
          <div className={`supplementary-report-card__attachments${attachments.length === 1 ? " supplementary-report-card__attachments--single" : ""}`} aria-label="患者补充的报告">
            {images.map((file) => (
              <button type="button" className="supplementary-report-attachment supplementary-report-attachment--image" key={file.id} disabled={!file.url || !preview} onClick={() => openAttachment(file)}>
                {file.url ? <img src={file.url} alt={file.name} loading="lazy" /> : <span className="supplementary-report-attachment__placeholder"><ImageIcon size={20} /></span>}
                <span className="supplementary-report-attachment__overlay"><Eye size={15} />预览</span>
                <span className="supplementary-report-attachment__caption">{file.name}</span>
              </button>
            ))}
            {files.map((file) => (
              <button type="button" className="supplementary-report-attachment supplementary-report-attachment--file" key={file.id} disabled={!file.url || !preview} onClick={() => openAttachment(file)}>
                <span className="supplementary-report-attachment__file-icon"><FileText size={20} /></span>
                <span className="supplementary-report-attachment__file-copy"><strong>{file.name}</strong>{file.size && <small>{file.size}</small>}</span>
                <Eye size={16} aria-hidden="true" />
              </button>
            ))}
          </div>
        ) : null}

        {isCompleted && attachments.length === 0 ? <div className="supplementary-report-card__empty supplementary-report-card__empty--compact"><FileText size={18} /><span>报告已上传，附件正在同步。</span></div> : null}

        <footer className="supplementary-report-card__footer">
          {viewed ? <span><Check size={14} />已查看患者补充报告</span> : isCompleted ? <span><Eye size={14} />点击附件预览报告</span> : <span>报告会保留在本次问诊记录中</span>}
        </footer>
      </article>
    </BlockShell>;
  }
  const title = asString(value.title) ?? "截图";
  const url = asString(value.url ?? value.src ?? value.image_url) ?? "";
  return <BlockShell block={block}><ReadOnlyCard title={title}>{url ? <figure className="block block--capture"><img src={url} alt={title} loading="lazy" /></figure> : <p><ImageIcon size={14} /></p>}</ReadOnlyCard></BlockShell>;
}
