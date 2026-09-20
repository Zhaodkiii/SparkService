"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { createPortal } from "react-dom";
import { usePathname } from "next/navigation";
import { ArrowUp, ClipboardPlus, FilePlus2, Image as ImageIcon, ListChecks, LoaderCircle, Paperclip, X } from "lucide-react";
import { ComposerImageStrip } from "@/components/chat/home/ComposerImageStrip";
import { useOptionalAuth } from "@/context/AuthContext";
import { useDoctorAuth } from "@/context/DoctorAuthGate";
import { useDoctorConversations } from "@/context/DoctorConversationsContext";
import { useOptionalDoctorRealtimeStatus } from "@/context/DoctorRealtimeStatusContext";
import { SparkChatImageApi } from "@/lib/api/chat-image-api";
import { SparkHospitalApi } from "@/lib/api/hospital-api";
import { shouldSubmitDoctorMessage } from "@/lib/hospital/composer-keyboard";
import { hospitalErrorMessage } from "@/lib/hospital/errors";
import {
  allAttachmentsReady,
  DEFAULT_ATTACHMENT_LIMITS,
  formatFileSize,
  hasPendingAttachment,
  newAttachmentDraft,
  readyAttachmentPayloads,
  removeAttachment,
  updateAttachment,
  validateAttachmentFile,
} from "@/lib/hospital/attachments";
import type { DoctorAttachmentDraft, DoctorAttachmentPayload } from "@/lib/hospital/attachments";
import { DEFAULT_QUICK_REPLIES } from "@/lib/hospital/quick-replies";
import type { QuickReply } from "@/lib/hospital/quick-replies";
import { useImageDrafts } from "@/lib/chat/use-image-drafts";
import type { ReadyImagePayload } from "@/lib/chat/image-drafts";
import { useAutoSizedTextarea } from "@/lib/use-auto-sized-textarea";
import type { ConversationAttachmentLimitsDTO, HospitalServiceStatus } from "@/types/hospital";
import type { DoctorRealtimeStatus } from "@/context/DoctorRealtimeStatusContext";

type ImageDrafts = ReturnType<typeof useImageDrafts>;

export type DoctorConsultAssistControl = {
  open: boolean;
  busy: boolean;
  error: string | null;
  onOpen: () => void;
  onClose: () => void;
  onSymptomCollection: () => void;
  onSupplementaryReport: () => void;
};

function DoctorConsultAssistDialog({ assist }: { assist: DoctorConsultAssistControl }) {
  useEffect(() => {
    if (!assist.open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !assist.busy) assist.onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [assist]);

  if (!assist.open || typeof document === "undefined") return null;

  return createPortal(
    <div className="doctor-consult-assist-dialog" role="presentation">
      <button type="button" className="doctor-consult-assist-dialog__scrim" aria-label="关闭问诊辅助" disabled={assist.busy} onClick={assist.onClose} />
      <section className="doctor-consult-assist-dialog__panel" role="dialog" aria-modal="true" aria-labelledby="doctor-consult-assist-dialog-title">
        <header className="doctor-consult-assist-dialog__head">
          <div>
            <h2 id="doctor-consult-assist-dialog-title">问诊辅助</h2>
            <p>选择要插入当前会话的辅助工具</p>
          </div>
          <button type="button" className="doctor-icon-button" aria-label="关闭问诊辅助" disabled={assist.busy} onClick={assist.onClose}>
            <X size={17} />
          </button>
        </header>
        <div className="doctor-consult-assist-dialog__body">
          <ul className="doctor-consult-assist-dialog__list">
            <li>
              <article className="doctor-consult-assist-dialog__item">
                <div className="doctor-consult-assist-dialog__item-copy">
                  <h3>症状采集</h3>
                  <p>插入症状采集卡后，患者直接描述不适，AI 会继续完成补充采集和确认。</p>
                </div>
                <button
                  type="button"
                  className="doctor-button doctor-consult-assist-dialog__action"
                  disabled={assist.busy}
                  onClick={() => void assist.onSymptomCollection()}
                >
                  {assist.busy ? <LoaderCircle size={14} className="spin" aria-hidden="true" /> : <ClipboardPlus size={14} aria-hidden="true" />}
                  {assist.busy ? "插入中…" : "插入症状采集卡"}
                </button>
              </article>
            </li>
            <li>
              <article className="doctor-consult-assist-dialog__item">
                <div className="doctor-consult-assist-dialog__item-copy">
                  <h3>补充报告</h3>
                  <p>向患者发送报告上传卡，支持拍摄、从相册选择或上传 PDF 等文件。</p>
                </div>
                <button
                  type="button"
                  className="doctor-button doctor-consult-assist-dialog__action"
                  disabled={assist.busy}
                  onClick={() => void assist.onSupplementaryReport()}
                >
                  {assist.busy ? <LoaderCircle size={14} className="spin" aria-hidden="true" /> : <FilePlus2 size={14} aria-hidden="true" />}
                  {assist.busy ? "插入中…" : "发送补充报告卡"}
                </button>
              </article>
            </li>
          </ul>
          {assist.error ? <p className="doctor-consult-assist-dialog__error" role="alert">{assist.error}</p> : null}
        </div>
      </section>
    </div>,
    document.body,
  );
}

export interface DoctorAttachmentOrchestration {
  drafts: DoctorAttachmentDraft[];
  limits: ConversationAttachmentLimitsDTO;
  select: (files: File[]) => void;
  retry: (id: string) => void;
  remove: (id: string) => void;
  clear: () => void;
}

export function DoctorComposerView({
  serviceStatus,
  doctorLabel,
  busy = false,
  error = null,
  onJoin,
  onSend,
  imageDrafts = null,
  attachments = null,
  quickReplies = DEFAULT_QUICK_REPLIES,
  connection = "connected",
  consultAssist = null,
  showIdentityHint = true,
}: {
  serviceStatus: HospitalServiceStatus | null;
  doctorLabel: string;
  busy?: boolean;
  error?: string | null;
  onJoin?: () => Promise<boolean> | boolean;
  onSend?: (text: string, images: ReadyImagePayload[], documents: DoctorAttachmentPayload[]) => Promise<boolean> | boolean;
  /** CHAT-WEB-029：图片草稿编排；为空时退化为纯文本输入框（测试/降级）。 */
  imageDrafts?: ImageDrafts | null;
  /** DOCTOR-WORKSPACE-000004：问诊附件（PDF 等）编排。 */
  attachments?: DoctorAttachmentOrchestration | null;
  /** DOCTOR-WORKSPACE-000004 第 12 问：常用语只填充输入框，不自动发送。 */
  quickReplies?: QuickReply[];
  /** DOCTOR-WORKSPACE-000004 第 15 问：断线禁止发送。 */
  connection?: DoctorRealtimeStatus;
  /** 线上问诊：输入框工具栏内的问诊辅助（如症状采集）。 */
  consultAssist?: DoctorConsultAssistControl | null;
  /** 线上问诊页不展示「以 xx · 真人医生身份回复」提示。 */
  showIdentityHint?: boolean;
}) {
  const [value, setValue] = useState("");
  const [imageHint, setImageHint] = useState<string | null>(null);
  const [showQuickReplies, setShowQuickReplies] = useState(false);
  const ref = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const attachmentInputRef = useRef<HTMLInputElement | null>(null);
  useAutoSizedTextarea(ref, value, 54, 190);

  if (!serviceStatus || serviceStatus === "ai_active") {
    return (
      <div className="composer-shell doctor-composer-state">
        <button type="button" className="doctor-button" disabled={busy || !onJoin} onClick={() => void onJoin?.()}>接管后可回复</button>
        <p className="composer-status">当前由 AI 接待，接管后才能以医生身份回复。</p>
      </div>
    );
  }
  if (serviceStatus === "pending_doctor") {
    return (
      <div className="composer-shell doctor-composer-state">
        <button type="button" className="doctor-button" disabled={busy || !onJoin} onClick={() => void onJoin?.()}>接管问诊</button>
        {error ? <p className="composer-status" role="alert">{error}</p> : <p className="composer-status">接管问诊后才能回复该患者。</p>}
      </div>
    );
  }
  if (serviceStatus === "ended") {
    return (
      <div className="composer-shell doctor-composer-state">
        <div className="doctor-ended-banner">本次问诊已结束，历史消息仍可查看，不能继续回复。再次咨询需由患者发起新的问诊。</div>
        {error ? <p className="composer-status" role="alert">{error}</p> : null}
      </div>
    );
  }

  const drafts = imageDrafts?.drafts ?? [];
  const hasPending = imageDrafts?.hasPending ?? false;
  const allReady = imageDrafts ? imageDrafts.allReady && drafts.length > 0 : false;
  const attachmentDrafts = attachments?.drafts ?? [];
  const attachmentsReady = attachments ? allAttachmentsReady(attachmentDrafts) : false;
  const attachmentsPending = hasPendingAttachment(attachmentDrafts);
  const disconnected = connection === "disconnected" || connection === "failed";

  const onFilesSelected = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length || !imageDrafts) return;
    const result = imageDrafts.selectImages(files);
    if (result.errorCode === "chat_image_count_exceeded") setImageHint(`最多发送 ${imageDrafts.maxDrafts} 张图片`);
    else setImageHint(null);
  };

  const onAttachmentsSelected = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length || !attachments) return;
    attachments.select(files);
  };

  const applyQuickReply = (reply: QuickReply) => {
    // 常用语仅填充输入框，由医生确认后手动发送（第 12 问）。
    setValue((current) => (current.trim() ? `${current.trim()}\n${reply.content}` : reply.content));
    setShowQuickReplies(false);
    ref.current?.focus();
  };

  const submit = async () => {
    if (busy || disconnected) return;
    if (hasPending) { setImageHint("图片尚未上传完成"); return; }
    if (attachmentsPending) { setImageHint("附件尚未上传完成"); return; }
    const text = value.trim();
    if (!text && !allReady && !attachmentsReady) return;
    setImageHint(null);
    const images = imageDrafts?.readyImages ?? [];
    const documents = attachments ? readyAttachmentPayloads(attachmentDrafts) : [];
    imageDrafts?.markSending();
    const accepted = await onSend?.(text, images, documents);
    if (accepted) {
      setValue("");
      imageDrafts?.clear();
      attachments?.clear();
    } else {
      // 发送失败：保留文本与图片/附件草稿（fileId 不丢），可直接重试。
      imageDrafts?.resetForRetry();
    }
  };

  const sendDisabled = disconnected || (!value.trim() && !allReady && !attachmentsReady) || hasPending || attachmentsPending || busy;
  const statusText = disconnected
    ? (connection === "failed" ? "无法恢复实时连接，请重新进入工作台；已禁止发送。" : "实时连接已断开，正在自动重连；恢复前不能发送。")
    : imageHint
      ?? (hasPending ? "图片尚未上传完成" : null)
      ?? (attachmentsPending ? "附件尚未上传完成" : null)
      ?? consultAssist?.error
      ?? error
      ?? null;

  return (
    <div className="composer-shell">
      {showIdentityHint ? <p className="doctor-composer-identity">以“{doctorLabel} · 真人医生”身份回复</p> : null}
      <div className="composer" aria-label="医生回复编辑器">
        {imageDrafts ? <ComposerImageStrip drafts={drafts} onRetry={imageDrafts.retry} onRemove={imageDrafts.remove} /> : null}
        {attachments && attachmentDrafts.length ? (
          <ul className="doctor-attachment-strip" aria-label="问诊附件">
            {attachmentDrafts.map((draft) => (
              <li key={draft.id} data-status={draft.status}>
                <Paperclip size={14} aria-hidden="true" />
                <span className="doctor-attachment-strip__name">{draft.fileName}</span>
                <em>{formatFileSize(draft.fileSize)}</em>
                {draft.status === "uploading" ? <span>上传中…</span> : null}
                {draft.status === "failed" ? (
                  <>
                    <span role="alert">{draft.error ?? "上传失败"}</span>
                    <button type="button" onClick={() => attachments.retry(draft.id)}>重试</button>
                  </>
                ) : null}
                <button type="button" aria-label={`移除附件 ${draft.fileName}`} onClick={() => attachments.remove(draft.id)}>×</button>
              </li>
            ))}
          </ul>
        ) : null}
        <textarea
          ref={ref}
          value={value}
          disabled={busy}
          aria-label="医生回复"
          placeholder="输入回复内容…"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (shouldSubmitDoctorMessage(event)) {
              event.preventDefault();
              void submit();
            }
          }}
        />
        <div className="composer__footer">
          <div className="composer__tools">
            {imageDrafts ? (
              <>
                <button className="composer-icon" type="button" aria-label="添加图片" title="添加图片" onClick={() => fileInputRef.current?.click()}>
                  <ImageIcon size={17} />
                </button>
                <input ref={fileInputRef} type="file" accept="image/*" multiple hidden aria-hidden="true" tabIndex={-1} onChange={onFilesSelected} />
              </>
            ) : null}
            {attachments ? (
              <>
                <button className="composer-icon" type="button" aria-label="上传附件" title="上传附件（PDF/JPG/PNG）" onClick={() => attachmentInputRef.current?.click()}>
                  <Paperclip size={17} />
                </button>
                <input ref={attachmentInputRef} type="file" accept=".pdf,.jpg,.jpeg,.png" multiple hidden aria-hidden="true" tabIndex={-1} onChange={onAttachmentsSelected} />
              </>
            ) : null}
            {consultAssist ? (
              <button
                className="composer-icon"
                type="button"
                aria-label="问诊辅助"
                title="问诊辅助"
                aria-haspopup="dialog"
                aria-expanded={consultAssist.open}
                disabled={consultAssist.busy}
                onClick={() => {
                  setShowQuickReplies(false);
                  consultAssist.onOpen();
                }}
              >
                {consultAssist.busy ? <LoaderCircle size={17} className="spin" aria-hidden="true" /> : <ClipboardPlus size={17} aria-hidden="true" />}
              </button>
            ) : null}
            {quickReplies.length ? (
              <span className="doctor-quick-replies">
                <button
                  className="composer-icon"
                  type="button"
                  aria-label="常用语"
                  title="常用语"
                  aria-expanded={showQuickReplies}
                  onClick={() => {
                    if (consultAssist?.open) consultAssist.onClose();
                    setShowQuickReplies((current) => !current);
                  }}
                >
                  <ListChecks size={17} />
                </button>
                {showQuickReplies ? (
                  <ul className="doctor-quick-replies__list" role="menu" aria-label="常用语列表">
                    {quickReplies.map((reply) => (
                      <li key={reply.id}>
                        <button type="button" role="menuitem" onClick={() => applyQuickReply(reply)}>
                          <strong>{reply.title}</strong>
                          <span>{reply.content}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </span>
            ) : null}
            <p className="doctor-composer-hint">Enter 换行 · Cmd/Ctrl + Enter 发送</p>
          </div>
          <button className="send-button" type="button" aria-label="发送" onClick={() => void submit()} disabled={sendDisabled}>
            <ArrowUp size={18} strokeWidth={2.2} />
          </button>
        </div>
      </div>
      {statusText ? <div className="composer-status" aria-live="polite">{statusText}</div> : null}
      {consultAssist ? <DoctorConsultAssistDialog assist={consultAssist} /> : null}
    </div>
  );
}

export function DoctorComposer({ consultAssistEnabled = false }: { consultAssistEnabled?: boolean } = {}) {
  const pathname = usePathname();
  const isConsultWorkspace = consultAssistEnabled || (pathname ?? "").startsWith("/doctor/consult");
  const { doctor } = useDoctorAuth();
  const conversations = useDoctorConversations();
  const auth = useOptionalAuth();
  const realtime = useOptionalDoctorRealtimeStatus();
  const status = conversations.detail?.service_status ?? null;
  const threadId = conversations.selectedThreadId;
  const [assistOpen, setAssistOpen] = useState(false);
  const [assistBusy, setAssistBusy] = useState(false);
  const [assistError, setAssistError] = useState<string | null>(null);
  // 医生发图是人对人消息，不经过 AI 模型，不依赖 supports_image_input 能力
  const imageApi = useMemo(() => (auth ? new SparkChatImageApi(auth.client) : null), [auth]);
  const hospitalApi = useMemo(() => (auth ? new SparkHospitalApi(auth.client) : null), [auth]);
  const imageDrafts = useImageDrafts({
    api: imageApi,
    threadId: conversations.selectedThreadId,
    supportsImageInput: true,
  });

  // DOCTOR-WORKSPACE-000004 第 16/17 问：问诊附件（PDF/JPG/PNG）上传编排。
  const [attachmentDrafts, setAttachmentDrafts] = useState<DoctorAttachmentDraft[]>([]);
  const [attachmentLimits, setAttachmentLimits] = useState<ConversationAttachmentLimitsDTO>(DEFAULT_ATTACHMENT_LIMITS);
  const attachmentFilesRef = useRef<Map<string, File>>(new Map());

  const uploadAttachment = (draftId: string) => {
    const api = hospitalApi;
    const threadId = conversations.selectedThreadId;
    const file = attachmentFilesRef.current.get(draftId);
    if (!api || !threadId || !file) return;
    setAttachmentDrafts((current) => updateAttachment(current, draftId, { status: "uploading", error: undefined }));
    void api
      .uploadConversationAttachment(threadId, file)
      .then((result) => {
        setAttachmentLimits(result.limits);
        setAttachmentDrafts((current) =>
          updateAttachment(current, draftId, {
            status: "ready",
            fileId: result.file_id,
            fileUuid: result.file_uuid,
            displayUrl: result.display_url,
            fileSize: result.file_size,
          }),
        );
      })
      .catch((cause) => {
        setAttachmentDrafts((current) => updateAttachment(current, draftId, { status: "failed", error: hospitalErrorMessage(cause) }));
      });
  };

  const attachments: DoctorAttachmentOrchestration = {
    drafts: attachmentDrafts,
    limits: attachmentLimits,
    select: (files) => {
      for (const file of files) {
        const draft = newAttachmentDraft(file);
        const error = validateAttachmentFile(file, attachmentLimits);
        attachmentFilesRef.current.set(draft.id, file);
        setAttachmentDrafts((current) => {
          if (current.length >= attachmentLimits.max_count) return current;
          return [...current, error ? { ...draft, status: "failed", error } : draft];
        });
        if (!error) uploadAttachment(draft.id);
      }
    },
    retry: (id) => uploadAttachment(id),
    remove: (id) => {
      attachmentFilesRef.current.delete(id);
      setAttachmentDrafts((current) => removeAttachment(current, id));
    },
    clear: () => {
      attachmentFilesRef.current.clear();
      setAttachmentDrafts([]);
    },
  };

  const onSymptomCollection = async () => {
    if (!hospitalApi || !threadId || assistBusy || status === "ended") return;
    setAssistBusy(true);
    setAssistError(null);
    try {
      await hospitalApi.createSymptomCollection(threadId);
      await conversations.reloadSelected();
      setAssistOpen(false);
    } catch {
      setAssistError("发起症状采集失败，请刷新后重试");
    } finally {
      setAssistBusy(false);
    }
  };

  const onSupplementaryReport = async () => {
    if (!hospitalApi || !threadId || assistBusy || status === "ended") return;
    setAssistBusy(true);
    setAssistError(null);
    try {
      await hospitalApi.createSupplementaryReportRequest(threadId);
      await conversations.reloadSelected();
      setAssistOpen(false);
    } catch {
      setAssistError("发送补充报告卡失败，请刷新后重试");
    } finally {
      setAssistBusy(false);
    }
  };

  const consultAssist =
    isConsultWorkspace && threadId
      ? {
          open: assistOpen,
          busy: assistBusy,
          error: assistError,
          onOpen: () => setAssistOpen(true),
          onClose: () => {
            if (assistBusy) return;
            setAssistOpen(false);
          },
          onSymptomCollection,
          onSupplementaryReport,
        }
      : null;

  return (
    <DoctorComposerView
      serviceStatus={status}
      doctorLabel={doctor.display_name}
      busy={conversations.writeBusy}
      error={conversations.writeError}
      onJoin={conversations.join}
      onSend={conversations.sendMessage}
      imageDrafts={imageDrafts}
      attachments={attachments}
      connection={realtime?.status ?? "connecting"}
      consultAssist={consultAssist}
      showIdentityHint={!isConsultWorkspace}
    />
  );
}
