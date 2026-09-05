"use client";

import { useState } from "react";
import { Download, Image as ImageIcon, Paperclip } from "lucide-react";
import { asRecord, asString, BlockShell, blockValue, blockValueObject, ReadOnlyCard } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";

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
function GalleryImageView({ image, index, total }: { image: GalleryImage; index: number; total: number }) {
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  if (failed) {
    return <figure className="gallery-item gallery-item--failed" role="status">
      <ImageIcon size={18} aria-hidden="true" />
      <strong>图片加载失败</strong>
      <span className="gallery-item__label">{image.filename ?? image.caption ?? `共 ${total} 张图片`}</span>
      <button type="button" onClick={() => { setAttempt((count) => count + 1); setFailed(false); }}>重试加载</button>
    </figure>;
  }
  const src = attempt > 0 ? `${image.url}${image.url.includes("?") ? "&" : "?"}retry=${attempt}` : image.url;
  return <figure className="gallery-item">
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
  const value = blockValue(block);
  const list = Array.isArray(value) ? value : (asRecord(value).files ?? asRecord(value).items ?? Object.values(asRecord(value)).find(Array.isArray));
  const files = asList(list).map((item) => ({
    name: asString(item.filename ?? item.name ?? item.title) ?? "问诊附件",
    url: asString(item.url ?? item.href),
    size: formatAttachmentSize(item.file_size ?? item.size),
    mime: asString(item.mime_type),
  }));
  return <BlockShell block={block}><ReadOnlyCard title="问诊附件">
    {files.length === 0 ? null : <ul className="block block--files" role="list">{files.map((file, index) => <li key={index}><Paperclip size={14} /><span>{file.name}</span>{file.size && <em>{file.size}</em>}{file.url && <a href={file.url} target="_blank" rel="noreferrer noopener" aria-label={`下载 ${file.name}`}><Download size={14} /></a>}</li>)}</ul>}
  </ReadOnlyCard></BlockShell>;
}

export function CaptureCardBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const title = asString(value.title) ?? "截图";
  const url = asString(value.url ?? value.src ?? value.image_url) ?? "";
  return <BlockShell block={block}><ReadOnlyCard title={title}>{url ? <figure className="block block--capture"><img src={url} alt={title} loading="lazy" /></figure> : <p><ImageIcon size={14} /></p>}</ReadOnlyCard></BlockShell>;
}