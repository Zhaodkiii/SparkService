"use client";

import { useState } from "react";
import { Download, Eye, X } from "lucide-react";
import { openPreviewOnEnter, useAttachmentPreview } from "@/components/shared/AttachmentPreviewProvider";
import { GENDER_LABEL } from "@/lib/hospital/labels";
import type { ConversationAttachmentItemDTO, PatientWorkspaceDTO } from "@/types/hospital";

const UUID_FILENAME = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

function formatAttachmentTimestamp(value?: string | null): string {
  if (!value) return "";
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return "";
  const date = new Date(parsed);
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${d} ${hh}:${mm}`;
}

function displayAttachmentName(filename: string, kind: ConversationAttachmentItemDTO["kind"]): string {
  const trimmed = filename.trim();
  if (!trimmed) return kind === "image" ? "图片附件" : "文档附件";
  const ext = trimmed.includes(".") ? trimmed.slice(trimmed.lastIndexOf(".")) : "";
  if (UUID_FILENAME.test(trimmed) || trimmed.length > 36) {
    return kind === "image" ? `图片附件${ext}` : `文档附件${ext}`;
  }
  return trimmed;
}

function attachmentBadgeLabel(filename: string, kind: ConversationAttachmentItemDTO["kind"]): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf") return "PDF";
  if (kind === "image" || ["jpg", "jpeg", "png", "webp", "gif", "heic"].includes(ext)) {
    if (ext === "jpeg") return "JPG";
    return ext ? ext.toUpperCase().slice(0, 4) : "JPG";
  }
  return ext ? ext.toUpperCase().slice(0, 4) : "DOC";
}

function attachmentBadgeVariant(filename: string, kind: ConversationAttachmentItemDTO["kind"]): "pdf" | "image" | "document" {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf") return "pdf";
  if (kind === "image" || ["jpg", "jpeg", "png", "webp", "gif", "heic"].includes(ext)) return "image";
  return "document";
}

function AttachmentFileBadge({ filename, kind }: { filename: string; kind: ConversationAttachmentItemDTO["kind"] }) {
  const variant = attachmentBadgeVariant(filename, kind);
  return (
    <span className={`consult-file-badge consult-file-badge--${variant}`} aria-hidden="true">
      {attachmentBadgeLabel(filename, kind)}
    </span>
  );
}

function ProfileItem({
  label,
  value,
  hideWhenEmpty = true,
  span = 1,
}: {
  label: string;
  value: string | number | null | undefined;
  hideWhenEmpty?: boolean;
  span?: 1 | 2;
}) {
  const empty = value === null || value === undefined || value === "";
  if (hideWhenEmpty && empty) return null;
  return (
    <p className={`consult-profile__item${span === 2 ? " consult-profile__item--wide" : ""}`}>
      <span>{label}</span>
      <em>{empty ? "未填写" : value}</em>
    </p>
  );
}

function PatientProfileCard({
  profile,
  consultNo,
  doctorName,
}: {
  profile: PatientWorkspaceDTO | null;
  consultNo?: string;
  doctorName?: string | null;
}) {
  if (!profile) {
    return (
      <section className="consult-section" aria-label="患者基础资料">
        <header className="consult-section__head"><h3>患者基础资料（只读）</h3></header>
        <p className="patient-module__hint">正在加载患者资料…</p>
      </section>
    );
  }
  const { patient, health_profile: health, medical_safety: safety } = profile;
  const items = [
    <ProfileItem key="consult-no" label="问诊编号" value={consultNo ?? "未填写"} hideWhenEmpty={false} span={2} />,
    <ProfileItem key="name" label="姓名" value={patient.display_name} hideWhenEmpty={false} />,
    <ProfileItem key="gender" label="性别" value={GENDER_LABEL[patient.gender] ?? "未填写"} hideWhenEmpty={false} />,
    <ProfileItem key="age" label="年龄" value={patient.age !== null ? `${patient.age} 岁` : null} hideWhenEmpty={false} />,
    <ProfileItem key="height" label="身高" value={health.height_cm !== null ? `${health.height_cm} cm` : null} hideWhenEmpty={false} />,
    <ProfileItem key="weight" label="体重" value={health.weight_kg !== null ? `${health.weight_kg} kg` : null} hideWhenEmpty={false} />,
    <ProfileItem key="bmi" label="BMI" value={health.bmi !== null ? String(health.bmi) : null} hideWhenEmpty={false} />,
    <ProfileItem key="doctor" label="已接诊医生" value={doctorName ?? null} hideWhenEmpty={false} />,
    <ProfileItem key="allergy" label="过敏史" value={safety.allergies.length ? safety.allergies.join("、") : "无"} hideWhenEmpty={false} span={2} />,
    <ProfileItem key="history" label="慢性病史" value={safety.past_medical_history.length ? safety.past_medical_history.join("、") : "无"} hideWhenEmpty={false} span={2} />,
  ];

  return (
    <section className="consult-section" aria-label="患者基础资料">
      <header className="consult-section__head"><h3>患者基础资料（只读）</h3></header>
      {items.length ? (
        <div className="consult-profile__grid">{items}</div>
      ) : (
        <p className="patient-module__hint">暂无已填写的患者资料。</p>
      )}
    </section>
  );
}

function AttachmentsCard({ items }: { items: ConversationAttachmentItemDTO[] | null }) {
  const [expanded, setExpanded] = useState(false);
  const preview = useAttachmentPreview();
  const openPreview = (item: ConversationAttachmentItemDTO) => {
    if (!item.url) return;
    preview.open({
      url: item.url,
      filename: displayAttachmentName(item.filename, item.kind),
      mime_type: item.mime_type,
      kind: item.kind,
    });
  };
  if (items === null) {
    return (
      <section className="consult-section" aria-label="病历与附件">
        <header className="consult-section__head"><h3>病历与附件</h3></header>
        <p className="patient-module__hint">正在加载附件…</p>
      </section>
    );
  }
  const visible = expanded ? items : items.slice(0, 8);
  return (
    <section className="consult-section" aria-label="病历与附件">
      <header className="consult-section__head">
        <h3>病历与附件</h3>
        <span>{items.length ? `共 ${items.length} 个` : null}</span>
      </header>
      {items.length === 0 ? <p className="patient-module__hint">本次问诊暂无附件。</p> : (
        <ul className="consult-attachment-list consult-attachment-list--compact">
          {visible.map((item, index) => {
            const label = displayAttachmentName(item.filename, item.kind);
            return (
              <li
                key={`${item.file_id ?? index}-${index}`}
                className="consult-attachment-list__row"
                role="button"
                tabIndex={0}
                onClick={() => openPreview(item)}
                onKeyDown={openPreviewOnEnter(() => openPreview(item))}
              >
                <AttachmentFileBadge filename={item.filename} kind={item.kind} />
                <span className="consult-attachment-list__name">
                  <strong title={item.filename}>{label}</strong>
                  {item.created_at ? <em>{formatAttachmentTimestamp(item.created_at)}</em> : null}
                </span>
                {item.url ? (
                  <span className="consult-attachment-list__actions">
                    <button type="button" aria-label={`预览 ${label}`} onClick={(event) => { event.stopPropagation(); openPreview(item); }}><Eye size={14} /></button>
                    <a href={item.url} download aria-label={`下载 ${label}`} onClick={(event) => event.stopPropagation()}><Download size={14} /></a>
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {items.length > 8 ? (
        <button type="button" className="patient-aux-link" onClick={() => setExpanded((current) => !current)}>
          {expanded ? "收起附件" : `查看全部附件（${items.length}）`}
        </button>
      ) : null}
    </section>
  );
}

/** 患者基础资料 + 病历附件：activity-panel 侧栏（默认收起）。 */
export function ConsultPatientProfilePanel({
  open,
  onClose,
  profile,
  attachments,
  consultNo,
  doctorName,
}: {
  open: boolean;
  onClose: () => void;
  profile: PatientWorkspaceDTO | null;
  attachments: ConversationAttachmentItemDTO[] | null;
  consultNo?: string;
  doctorName?: string | null;
}) {
  return (
    <aside
      className={`activity-panel consult-profile-panel${open ? " activity-panel--open" : ""}`}
      aria-hidden={!open}
      aria-label="患者基础资料"
    >
      <header>
        <div>
          <p>患者基础资料</p>
          <span>只读 · 含本次问诊附件</span>
        </div>
        <button className="icon-button" type="button" aria-label="关闭患者资料" onClick={onClose}>
          <X size={17} />
        </button>
      </header>
      <div className="activity-panel__body consult-profile-panel__body">
        <PatientProfileCard profile={profile} consultNo={consultNo} doctorName={doctorName} />
        <AttachmentsCard items={attachments} />
      </div>
    </aside>
  );
}
