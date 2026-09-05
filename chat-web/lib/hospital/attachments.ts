/** DOCTOR-WORKSPACE-000004 第 16/17 问：医生问诊附件（PDF/JPG/PNG）客户端编排。
 *
 * 纯逻辑模块：客户端先做类型/大小预检（真正约束在服务端），上传成功后
 * 得到 file_id 随消息发送；失败保留草稿并允许医生手动重试。
 */

import type { ConversationAttachmentLimitsDTO } from "@/types/hospital";

export const DEFAULT_ATTACHMENT_LIMITS: ConversationAttachmentLimitsDTO = {
  max_bytes: 20 * 1024 * 1024,
  max_count: 5,
  allowed_mime_types: ["application/pdf", "image/jpeg", "image/png"],
};

export type DoctorAttachmentStatus = "uploading" | "ready" | "failed";

export interface DoctorAttachmentDraft {
  id: string;
  fileName: string;
  mimeType: string;
  fileSize: number;
  status: DoctorAttachmentStatus;
  /** 上传成功后由服务端返回。 */
  fileId?: number;
  fileUuid?: string;
  displayUrl?: string;
  error?: string;
}

/** 服务端发送消息时 attachments 数组项。 */
export interface DoctorAttachmentPayload {
  file_id: number;
  type: "image" | "document";
  order: number;
  mime_type: string;
  file_size?: number;
  display_url?: string;
  file_uuid?: string;
  filename?: string;
}

const MIME_BY_EXT: Record<string, string> = {
  pdf: "application/pdf",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
};

export function isImageMime(mimeType: string): boolean {
  return mimeType.startsWith("image/");
}

/** 客户端预检：返回可读错误；通过返回 null。真正约束以服务端为准。 */
export function validateAttachmentFile(
  file: Pick<File, "name" | "size" | "type">,
  limits: ConversationAttachmentLimitsDTO = DEFAULT_ATTACHMENT_LIMITS,
): string | null {
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  const mime = (file.type || MIME_BY_EXT[ext] || "").toLowerCase();
  if (!limits.allowed_mime_types.includes(mime) || MIME_BY_EXT[ext] !== mime) {
    return "仅支持 PDF、JPG、PNG 格式的附件";
  }
  if (file.size > limits.max_bytes) {
    const mb = Math.round(limits.max_bytes / 1024 / 1024);
    return `单个附件不能超过 ${mb} MB`;
  }
  return null;
}

export function newAttachmentDraft(file: File): DoctorAttachmentDraft {
  return {
    id: crypto.randomUUID(),
    fileName: file.name,
    mimeType: (file.type || "").toLowerCase(),
    fileSize: file.size,
    status: "uploading",
  };
}

export function updateAttachment(
  drafts: DoctorAttachmentDraft[],
  id: string,
  patch: Partial<Omit<DoctorAttachmentDraft, "id">>,
): DoctorAttachmentDraft[] {
  return drafts.map((draft) => (draft.id === id ? { ...draft, ...patch } : draft));
}

export function removeAttachment(drafts: DoctorAttachmentDraft[], id: string): DoctorAttachmentDraft[] {
  return drafts.filter((draft) => draft.id !== id);
}

export function allAttachmentsReady(drafts: DoctorAttachmentDraft[]): boolean {
  return drafts.length > 0 && drafts.every((draft) => draft.status === "ready");
}

export function hasPendingAttachment(drafts: DoctorAttachmentDraft[]): boolean {
  return drafts.some((draft) => draft.status === "uploading");
}

/** 已就绪草稿 → 发送 payload；发送成功后服务端按 file_id 重新解析。 */
export function readyAttachmentPayloads(drafts: DoctorAttachmentDraft[]): DoctorAttachmentPayload[] {
  return drafts
    .filter((draft) => draft.status === "ready" && typeof draft.fileId === "number")
    .map((draft, order) => ({
      file_id: draft.fileId as number,
      type: isImageMime(draft.mimeType) ? "image" : "document",
      order,
      mime_type: draft.mimeType,
      file_size: draft.fileSize,
      display_url: draft.displayUrl,
      file_uuid: draft.fileUuid,
      filename: draft.fileName,
    }));
}

export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
