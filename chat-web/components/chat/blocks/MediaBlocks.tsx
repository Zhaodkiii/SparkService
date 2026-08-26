"use client";

import { Download, Image as ImageIcon, Paperclip } from "lucide-react";
import { asString, BlockShell, blockValueObject, ReadOnlyCard } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";

function asList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

export function ImageGalleryBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const images = asList(value.images ?? value.items).map((item) => ({ url: asString(item.url ?? item.src) ?? "", caption: asString(item.caption ?? item.alt ?? item.title) }));
  const valid = images.filter((image) => image.url);
  return <BlockShell block={block}><ReadOnlyCard title="图片">
    {valid.length === 0 ? null : <div className="block block--gallery" role="list">{valid.map((image, index) => <figure key={index} className="gallery-item"><img src={image.url} alt={image.caption ?? `图片 ${index + 1}`} loading="lazy" /><figcaption>{image.caption}</figcaption></figure>)}</div>}
  </ReadOnlyCard></BlockShell>;
}

export function FileAttachmentsBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const files = asList(value.files ?? value.attachments).map((item) => ({ name: asString(item.name ?? item.title ?? item.filename) ?? "附件", url: asString(item.url ?? item.href), size: asString(item.size) }));
  return <BlockShell block={block}><ReadOnlyCard title="附件">
    {files.length === 0 ? null : <ul className="block block--files" role="list">{files.map((file, index) => <li key={index}><Paperclip size={14} /><span>{file.name}</span>{file.size && <em>{file.size}</em>}{file.url && <a href={file.url} target="_blank" rel="noreferrer noopener" aria-label={`下载 ${file.name}`}><Download size={14} /></a>}</li>)}</ul>}
  </ReadOnlyCard></BlockShell>;
}

export function CaptureCardBlock({ block }: BlockRenderProps) {
  const value = blockValueObject(block);
  const title = asString(value.title) ?? "截图";
  const url = asString(value.url ?? value.src ?? value.image_url) ?? "";
  return <BlockShell block={block}><ReadOnlyCard title={title}>{url ? <figure className="block block--capture"><img src={url} alt={title} loading="lazy" /></figure> : <p><ImageIcon size={14} /></p>}</ReadOnlyCard></BlockShell>;
}