"use client";

import { useState, type MouseEvent } from "react";
import { ChevronRight, Download, Eye, Paperclip } from "lucide-react";
import { GalleryImageView } from "@/components/chat/blocks/MediaBlocks";
import { asString, BlockShell, blockValueObject } from "@/components/chat/blocks/common";
import type { BlockRenderProps } from "@/components/chat/blocks/common";
import { useOptionalAttachmentPreview } from "@/components/shared/AttachmentPreviewProvider";
import { SERVICE_STATUS_LABEL } from "@/lib/hospital/labels";

type AttachmentItem = {
  id: string;
  type: "image" | "document";
  url: string;
  filename: string;
  mime: string | null;
  size: string | null;
};

function formatSubmittedAt(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return null;
  const date = new Date(parsed);
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${m}月${d}日 ${hh}:${mm}`;
}

function formatAttachmentSize(value: unknown): string | null {
  const bytes = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function fileExtension(name: string): string {
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".") + 1).toUpperCase() : "";
  return ext || "FILE";
}

function asAttachments(value: Record<string, unknown>): AttachmentItem[] {
  const raw = Array.isArray(value.attachments) ? value.attachments : [];
  return raw
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    .map((item, index) => {
      const filename = asString(item.filename ?? item.name) ?? (item.type === "image" ? "图片" : "附件");
      const url = asString(item.url ?? item.display_url) ?? "";
      const type = asString(item.type) === "image" || asString(item.mime_type)?.startsWith("image/") ? "image" : "document";
      return {
        id: asString(item.id) ?? `${url}-${index}`,
        type,
        url,
        filename,
        mime: asString(item.mime_type),
        size: formatAttachmentSize(item.file_size ?? item.size),
      };
    })
    .filter((item) => item.url);
}

function ConsultationCardDetailModal({
  value,
  attachments,
  onClose,
}: {
  value: Record<string, unknown>;
  attachments: AttachmentItem[];
  onClose: () => void;
}) {
  const doctor = (value.doctor ?? {}) as Record<string, unknown>;
  const department = (value.department ?? {}) as Record<string, unknown>;
  const hospital = (value.hospital ?? {}) as Record<string, unknown>;
  const status = asString(value.service_status) ?? "";
  const rows = [
    ["问诊编号", asString(value.consult_no)],
    ["主诉", asString(value.chief_complaint)],
    ["科室", asString(department.name)],
    ["医院", asString(hospital.short_name) ?? asString(hospital.name)],
    ["接诊医生", asString(doctor.display_name)],
    ["职称", asString(doctor.title)],
    ["状态", SERVICE_STATUS_LABEL[status as keyof typeof SERVICE_STATUS_LABEL] ?? status],
    ["既往史", asString(value.past_history)],
    ["家族史", asString(value.family_history)],
    ["过敏史", asString(value.allergy_history)],
  ].filter(([, cell]) => cell);

  const orderItems = Array.isArray(value.order_items)
    ? value.order_items.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];

  return (
    <div className="consult-card-modal" role="dialog" aria-modal="true" aria-label="问诊详情">
      <button type="button" className="consult-card-modal__backdrop" aria-label="关闭" onClick={onClose} />
      <div className="consult-card-modal__panel">
        <header className="consult-card-modal__head">
          <h2>问诊详情</h2>
          <button type="button" className="doctor-button doctor-button--ghost" onClick={onClose}>关闭</button>
        </header>
        <div className="consult-card-modal__body">
          <dl className="consult-card-modal__grid">
            {rows.map(([label, cell]) => (
              <div key={label} className="consult-card-modal__row">
                <dt>{label}</dt>
                <dd>{cell}</dd>
              </div>
            ))}
          </dl>
          {orderItems.length ? (
            <section className="consult-card-modal__section">
              <h3>开单项目</h3>
              <p>{orderItems.join("、")}</p>
            </section>
          ) : null}
          {attachments.length ? (
            <section className="consult-card-modal__section">
              <h3>病历资料</h3>
              <ConsultationCardAttachments attachments={attachments} />
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ConsultationCardAttachments({ attachments }: { attachments: AttachmentItem[] }) {
  const preview = useOptionalAttachmentPreview();
  const images = attachments.filter((item) => item.type === "image");
  const files = attachments.filter((item) => item.type !== "image");
  const open = (item: AttachmentItem, event?: MouseEvent) => {
    event?.stopPropagation();
    if (!item.url || !preview) return;
    preview.open({
      url: item.url,
      filename: item.filename,
      mime_type: item.mime ?? undefined,
      kind: item.type === "image" ? "image" : "document",
    });
  };

  return (
    <div className="consult-card-block__attachments">
      {images.length ? (
        <div className="consult-card-block__gallery" role="list">
          {images.map((image, index) => (
            <GalleryImageView
              key={image.id}
              image={{ url: image.url, caption: null, filename: image.filename }}
              index={index}
              total={images.length}
            />
          ))}
        </div>
      ) : null}
      {files.length ? (
        <ul className="consult-card-block__files" role="list">
          {files.map((file) => (
            <li key={file.id}>
              <button type="button" className="consult-card-block__file" onClick={(event) => open(file, event)}>
                <span className="consult-card-block__file-icon" aria-hidden="true">
                  <Paperclip size={18} />
                  <em>{fileExtension(file.filename)}</em>
                </span>
                <span className="consult-card-block__file-meta">
                  <strong>{file.filename}</strong>
                  <span>{file.size ? `点击预览 · ${file.size}` : "点击预览"}</span>
                </span>
                <Eye size={16} aria-hidden="true" />
              </button>
              {file.url ? (
                <a href={file.url} download aria-label={`下载 ${file.filename}`} onClick={(event) => event.stopPropagation()}>
                  <Download size={14} />
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** 患者提交线上问诊时写入会话的问诊单卡片；医生端点击弹出详情，附件直接按消息附件样式展示。 */
export function ConsultationCardBlock({ block }: BlockRenderProps) {
  const [open, setOpen] = useState(false);
  const value = blockValueObject(block);
  const attachments = asAttachments(value);
  const doctor = (value.doctor ?? {}) as Record<string, unknown>;
  const department = (value.department ?? {}) as Record<string, unknown>;
  const hospital = (value.hospital ?? {}) as Record<string, unknown>;
  const doctorName = asString(doctor.display_name) ?? asString((value.agent as Record<string, unknown> | undefined)?.name) ?? "问诊医生";
  const title = asString(doctor.title);
  const status = asString(value.service_status) ?? "";
  const statusLabel = SERVICE_STATUS_LABEL[status as keyof typeof SERVICE_STATUS_LABEL] ?? status;
  const location = [asString(department.name), asString(hospital.short_name) ?? asString(hospital.name)].filter(Boolean).join(" · ");
  const complaint = asString(value.chief_complaint);
  const consultNo = asString(value.consult_no);
  const submittedAt = formatSubmittedAt(value.submitted_at);

  return (
    <>
      <BlockShell block={block}>
        <article className="consult-card-block">
          <button type="button" className="consult-card-block__hit" onClick={() => setOpen(true)}>
            <div className="consult-card-block__head">
              <strong>{doctorName}</strong>
              {title ? <span className="consult-card-block__title">{title}</span> : null}
              <span className={`consult-card-block__status consult-card-block__status--${status || "unknown"}`}>{statusLabel}</span>
            </div>
            {location ? <p className="consult-card-block__meta">{location}</p> : null}
            {complaint ? <p className="consult-card-block__complaint">主诉：{complaint}</p> : null}
          </button>
          {attachments.length ? <ConsultationCardAttachments attachments={attachments} /> : null}
          <button type="button" className="consult-card-block__foot" onClick={() => setOpen(true)}>
            {consultNo ? <span>问诊编号：{consultNo}</span> : null}
            {submittedAt ? <span>{submittedAt}</span> : null}
            <ChevronRight size={14} aria-hidden="true" />
          </button>
        </article>
      </BlockShell>
      {open ? <ConsultationCardDetailModal value={value} attachments={attachments} onClose={() => setOpen(false)} /> : null}
    </>
  );
}
