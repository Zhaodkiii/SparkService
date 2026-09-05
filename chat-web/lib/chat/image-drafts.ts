/**
 * 图片草稿状态机（CHAT-WEB-029 §18）。
 *
 * 纯逻辑模块，不依赖 React/DOM，便于单测。草稿只存活于页面生命周期内，
 * 不持久化到 localStorage/IndexedDB。
 *
 * 状态流转：
 * selected → processing → ready_to_upload → uploading → uploaded
 *   → registering → ready → sending → sent
 * processing/uploading/registering/sending → failed(retryable | non_retryable)
 */

/** 单条消息最多携带 3 张图片（与服务端校验一致）。 */
export const MAX_IMAGE_DRAFTS = 3;

export type ImageDraftStatus =
  | "selected"
  | "processing"
  | "ready_to_upload"
  | "uploading"
  | "uploaded"
  | "registering"
  | "ready"
  | "sending"
  | "sent"
  | "failed";

export interface ImageDraftError {
  /** 稳定业务错误码，如 chat_image_upload_failed。 */
  code: string;
  retryable: boolean;
}

export interface ImageDraft {
  id: string;
  fileName: string;
  /** 本地预览 object URL；移除/发送成功后由调用方 revoke。 */
  previewUrl: string;
  status: ImageDraftStatus;
  /** 上传进度 0-100，仅 uploading 阶段有意义。 */
  progress: number;
  fileId?: string;
  /** ManagedFile.file_uuid：作为 iOS ChatAttachment 必填的 id 字段透传。 */
  fileUuid?: string;
  displayUrl?: string;
  fileSize?: number;
  mimeType?: string;
  error?: ImageDraftError;
}

/** 追加草稿；最多保留 MAX_IMAGE_DRAFTS 张，超出部分放入 rejected。 */
export function addDrafts(
  drafts: ImageDraft[],
  incoming: ImageDraft[],
  max: number = MAX_IMAGE_DRAFTS,
): { drafts: ImageDraft[]; rejected: ImageDraft[] } {
  const room = Math.max(0, max - drafts.length);
  const accepted = incoming.slice(0, room);
  const rejected = incoming.slice(room);
  return { drafts: [...drafts, ...accepted], rejected };
}

/** 更新单张草稿；不存在的 id 原样返回。 */
export function updateDraft(
  drafts: ImageDraft[],
  id: string,
  patch: Partial<Omit<ImageDraft, "id">>,
): ImageDraft[] {
  return drafts.map((draft) => (draft.id === id ? { ...draft, ...patch } : draft));
}

/** 移除单张草稿。 */
export function removeDraft(drafts: ImageDraft[], id: string): ImageDraft[] {
  return drafts.filter((draft) => draft.id !== id);
}

/** 存在草稿且全部为 ready 时才允许发送。 */
export function allReady(drafts: ImageDraft[]): boolean {
  return drafts.length > 0 && drafts.every((draft) => draft.status === "ready");
}

/** 是否存在尚未 ready 的草稿（用于禁用发送并提示"图片尚未上传完成"）。 */
export function hasPendingDrafts(drafts: ImageDraft[]): boolean {
  return drafts.some((draft) => !["ready", "sending", "sent"].includes(draft.status));
}

/** 发送前将 ready 草稿标记为 sending。 */
export function markSending(drafts: ImageDraft[]): ImageDraft[] {
  return drafts.map((draft) => (draft.status === "ready" ? { ...draft, status: "sending" } : draft));
}

/** 发送成功后将 sending 草稿标记为 sent。 */
export function markSent(drafts: ImageDraft[]): ImageDraft[] {
  return drafts.map((draft) => (draft.status === "sending" ? { ...draft, status: "sent" } : draft));
}

/**
 * CreateRun 失败后的草稿回退：sending → ready，保留 fileId 不重新上传；
 * 其余状态保持不变（ready 草稿的 fileId 天然保留）。
 */
export function resetForRetry(drafts: ImageDraft[]): ImageDraft[] {
  return drafts.map((draft) => (draft.status === "sending" ? { ...draft, status: "ready" } : draft));
}

/** 已就绪图片的发送载荷（RunControlContext.createRun 的 images 入参）。 */
export interface ReadyImagePayload {
  fileId: string;
  /** ManagedFile.file_uuid，用于 iOS ChatAttachment.id（必填 UUID）。 */
  fileUuid?: string;
  displayUrl?: string;
  fileName: string;
  mimeType?: string;
  fileSize?: number;
  order: number;
}

/** 将 ready 草稿按选择顺序投影为发送载荷。 */
export function toReadyImagePayloads(drafts: ImageDraft[]): ReadyImagePayload[] {
  return drafts
    .filter((draft) => draft.status === "ready" && draft.fileId)
    .map((draft, index) => ({
      fileId: draft.fileId as string,
      fileUuid: draft.fileUuid,
      displayUrl: draft.displayUrl,
      fileName: draft.fileName,
      mimeType: draft.mimeType,
      fileSize: draft.fileSize,
      order: index,
    }));
}
