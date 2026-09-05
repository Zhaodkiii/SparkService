"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SparkChatImageApi } from "@/lib/api/chat-image-api";
import { SparkApiError } from "@/lib/api/http-client";
import type { ChatImageUploadSessionDTO } from "@/types/chat-image";
import { ImageNormalizeError, normalizeImageForUpload } from "@/lib/chat/image-normalize";
import { ImageUploadError, uploadWithProgress } from "@/lib/chat/image-upload";
import {
  MAX_IMAGE_DRAFTS,
  addDrafts,
  allReady,
  hasPendingDrafts,
  markSending,
  removeDraft,
  resetForRetry,
  toReadyImagePayloads,
  updateDraft,
} from "@/lib/chat/image-drafts";
import type { ImageDraft, ImageDraftError } from "@/lib/chat/image-drafts";

/** 未完成上传的草稿状态（能力降级时这些状态会被阻断）。 */
const INTERRUPTABLE_STATUSES: ReadonlySet<string> = new Set([
  "selected",
  "processing",
  "ready_to_upload",
  "uploading",
  "uploaded",
  "registering",
]);

/** 单张草稿的运行时上下文：跨阶段保留，重试时不重复已完成阶段。 */
interface DraftRuntime {
  file: File;
  clientUploadId: string;
  blob?: Blob;
  mimeType?: string;
  fileSize?: number;
  fileName?: string;
  session?: ChatImageUploadSessionDTO;
  uploaded?: boolean;
  abort?: AbortController;
}

/** 阶段失败：携带稳定错误码，由管线统一写入草稿。 */
class DraftStageError extends Error {
  readonly draftError: ImageDraftError;

  constructor(draftError: ImageDraftError) {
    super(draftError.code);
    this.name = "DraftStageError";
    this.draftError = draftError;
  }
}

/** 把各阶段异常归一化为草稿错误；优先保留服务端稳定错误码。 */
function asDraftError(cause: unknown, fallbackCode: string, fallbackRetryable: boolean): DraftStageError {
  if (cause instanceof DraftStageError) return cause;
  if (cause instanceof ImageNormalizeError || cause instanceof ImageUploadError) {
    return new DraftStageError({ code: cause.code, retryable: cause.retryable });
  }
  if (cause instanceof SparkApiError) {
    const details = cause.failure.details;
    const serverCode = details && typeof details === "object" && !Array.isArray(details)
      ? (details as Record<string, unknown>).error_code
      : undefined;
    return new DraftStageError({
      code: typeof serverCode === "string" ? serverCode : fallbackCode,
      retryable: cause.failure.retryable,
    });
  }
  return new DraftStageError({ code: fallbackCode, retryable: fallbackRetryable });
}

export interface SelectImagesResult {
  accepted: number;
  rejected: number;
  /** chat_image_capability_unavailable / chat_image_count_exceeded */
  errorCode?: string;
}

export interface UseImageDraftsInput {
  api: SparkChatImageApi | null;
  threadId: string | null;
  supportsImageInput: boolean;
}

/**
 * 图片草稿编排 Hook（CHAT-WEB-029）：选择 → 标准化 → 签发会话 → 直传 OSS
 * → 登记 ManagedFile → ready。失败草稿按阶段重试，不重复已完成阶段。
 */
export function useImageDrafts({ api, threadId, supportsImageInput }: UseImageDraftsInput) {
  const [drafts, setDrafts] = useState<ImageDraft[]>([]);
  const draftsRef = useRef<ImageDraft[]>([]);
  const runtimesRef = useRef<Map<string, DraftRuntime>>(new Map());
  const apiRef = useRef<SparkChatImageApi | null>(api);
  const threadIdRef = useRef<string | null>(threadId);
  const supportsImageInputRef = useRef(supportsImageInput);
  const mountedRef = useRef(true);

  useEffect(() => { apiRef.current = api; }, [api]);
  useEffect(() => { threadIdRef.current = threadId; }, [threadId]);
  useEffect(() => { supportsImageInputRef.current = supportsImageInput; }, [supportsImageInput]);
  useEffect(() => { draftsRef.current = drafts; }, [drafts]);

  const apply = useCallback((updater: (current: ImageDraft[]) => ImageDraft[]) => {
    if (!mountedRef.current) return;
    setDrafts(updater);
  }, []);

  const patchDraft = useCallback((id: string, patch: Partial<Omit<ImageDraft, "id">>) => {
    apply((current) => updateDraft(current, id, patch));
  }, [apply]);

  /** 单张草稿的处理管线；任一阶段失败即终止并标记 failed。 */
  const runPipeline = useCallback(async (id: string) => {
    const runtime = runtimesRef.current.get(id);
    const imageApi = apiRef.current;
    if (!runtime || !imageApi) return;
    try {
      // 阶段 1：标准化压缩
      if (!runtime.blob) {
        patchDraft(id, { status: "processing", error: undefined });
        let normalized;
        try {
          normalized = await normalizeImageForUpload(runtime.file);
        } catch (cause) {
          throw asDraftError(cause, "chat_image_normalize_failed", false);
        }
        runtime.blob = normalized.blob;
        runtime.mimeType = normalized.mimeType;
        runtime.fileSize = normalized.fileSize;
        runtime.fileName = normalized.fileName;
        patchDraft(id, { status: "ready_to_upload", mimeType: normalized.mimeType, fileSize: normalized.fileSize });
      }
      // 阶段 2：签发上传会话（client_upload_id 幂等）
      if (!runtime.session) {
        let session: ChatImageUploadSessionDTO;
        try {
          session = await imageApi.createUploadSession({
            purpose: "chat_image",
            thread_id: threadIdRef.current,
            mime_type: runtime.mimeType ?? "image/webp",
            file_size: runtime.fileSize ?? runtime.blob.size,
            client_upload_id: runtime.clientUploadId,
          });
        } catch (cause) {
          throw asDraftError(cause, "chat_image_upload_failed", true);
        }
        runtime.session = session;
      }
      // 阶段 3：直传 OSS
      if (!runtime.uploaded) {
        const controller = new AbortController();
        runtime.abort = controller;
        patchDraft(id, { status: "uploading", progress: 0 });
        try {
          await uploadWithProgress(
            runtime.session.upload_url,
            runtime.session.required_headers,
            runtime.blob,
            (progress) => patchDraft(id, { progress }),
            controller.signal,
          );
        } catch (cause) {
          if (cause instanceof ImageUploadError && cause.code === "chat_image_upload_cancelled") return;
          // 上传 URL 可能已过期，重试时重新签发会话。
          runtime.session = undefined;
          throw asDraftError(cause, "chat_image_upload_failed", true);
        } finally {
          runtime.abort = undefined;
        }
        runtime.uploaded = true;
        patchDraft(id, { status: "uploaded", progress: 100 });
      }
      // 阶段 4：登记 ManagedFile（client_upload_id 幂等，重复返回同一 file_id）
      patchDraft(id, { status: "registering" });
      let fileId: string;
      let fileUuid: string;
      let displayUrl: string;
      try {
        const completed = await imageApi.completeUpload(runtime.session.upload_session_id, {
          client_upload_id: runtime.clientUploadId,
          object_key: runtime.session.object_key,
          mime_type: runtime.mimeType ?? "image/webp",
          file_size: runtime.fileSize ?? runtime.blob.size,
        });
        fileId = completed.file_id;
        fileUuid = completed.file_uuid;
        displayUrl = completed.display_url;
      } catch (cause) {
        throw asDraftError(cause, "chat_image_registration_failed", true);
      }
      patchDraft(id, { status: "ready", fileId, fileUuid, displayUrl, error: undefined });
    } catch (cause) {
      const staged = asDraftError(cause, "chat_image_upload_failed", true);
      patchDraft(id, { status: "failed", error: staged.draftError });
    }
  }, [patchDraft]);

  /** 选择图片：capability 关闭时整体拒绝；超过 3 张时拒绝多余部分。 */
  const selectImages = useCallback((files: File[]): SelectImagesResult => {
    if (!supportsImageInputRef.current || !apiRef.current) {
      return { accepted: 0, rejected: files.length, errorCode: "chat_image_capability_unavailable" };
    }
    const incoming: ImageDraft[] = files.map((file) => ({
      id: crypto.randomUUID(),
      fileName: file.name || "image",
      previewUrl: URL.createObjectURL(file),
      status: "selected",
      progress: 0,
    }));
    const { drafts: next, rejected } = addDrafts(draftsRef.current, incoming);
    const accepted = next.slice(draftsRef.current.length);
    // 被拒绝的草稿不进入状态，立即释放预览 URL。
    for (const draft of rejected) URL.revokeObjectURL(draft.previewUrl);
    setDrafts(next);
    accepted.forEach((draft, index) => {
      runtimesRef.current.set(draft.id, { file: files[index], clientUploadId: crypto.randomUUID() });
    });
    for (const draft of accepted) void runPipeline(draft.id);
    return {
      accepted: accepted.length,
      rejected: rejected.length,
      errorCode: rejected.length > 0 ? "chat_image_count_exceeded" : undefined,
    };
  }, [runPipeline]);

  /** 从失败阶段重试；已完成的压缩/会话/直传阶段不会重复。 */
  const retry = useCallback((id: string) => {
    const draft = draftsRef.current.find((item) => item.id === id);
    if (!draft || draft.status !== "failed" || !supportsImageInputRef.current) return;
    apply((current) => updateDraft(current, id, { status: "selected", error: undefined, progress: 0 }));
    void runPipeline(id);
  }, [apply, runPipeline]);

  /** 移除草稿：取消进行中的上传监听并释放预览 URL。 */
  const remove = useCallback((id: string) => {
    const runtime = runtimesRef.current.get(id);
    runtime?.abort?.abort();
    runtimesRef.current.delete(id);
    const draft = draftsRef.current.find((item) => item.id === id);
    if (draft) URL.revokeObjectURL(draft.previewUrl);
    apply((current) => removeDraft(current, id));
  }, [apply]);

  /** 发送成功后清空全部草稿并释放预览 URL。 */
  const clear = useCallback(() => {
    for (const runtime of runtimesRef.current.values()) runtime.abort?.abort();
    runtimesRef.current.clear();
    for (const draft of draftsRef.current) URL.revokeObjectURL(draft.previewUrl);
    apply(() => []);
  }, [apply]);

  const markSendingDrafts = useCallback(() => apply(markSending), [apply]);
  const resetDraftsForRetry = useCallback(() => apply(resetForRetry), [apply]);

  // 能力降级（切换模型/线程后 supports_image_input 变 false）：
  // 取消未完成上传的草稿并标记失败；ready 草稿保留 fileId，不自动重传。
  useEffect(() => {
    if (supportsImageInput) return;
    for (const draft of draftsRef.current) {
      if (!INTERRUPTABLE_STATUSES.has(draft.status)) continue;
      runtimesRef.current.get(draft.id)?.abort?.abort();
      apply((current) => updateDraft(current, draft.id, {
        status: "failed",
        error: { code: "chat_image_capability_unavailable", retryable: false },
      }));
    }
  }, [supportsImageInput, apply]);

  // 卸载时取消全部上传并释放预览 URL。
  useEffect(() => {
    mountedRef.current = true;
    const runtimes = runtimesRef.current;
    const draftsSnapshot = draftsRef;
    return () => {
      mountedRef.current = false;
      for (const runtime of runtimes.values()) runtime.abort?.abort();
      runtimes.clear();
      for (const draft of draftsSnapshot.current) URL.revokeObjectURL(draft.previewUrl);
    };
  }, []);

  const readyImages = useMemo(() => toReadyImagePayloads(drafts), [drafts]);

  return {
    drafts,
    maxDrafts: MAX_IMAGE_DRAFTS,
    allReady: allReady(drafts),
    hasPending: hasPendingDrafts(drafts),
    readyImages,
    selectImages,
    retry,
    remove,
    clear,
    markSending: markSendingDrafts,
    resetForRetry: resetDraftsForRetry,
  };
}
