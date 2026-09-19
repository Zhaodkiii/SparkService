"use client";

import { useState } from "react";
import { HeartPulse, ShieldCheck } from "lucide-react";
import { ChatBlockRenderer } from "@/components/chat/home/ChatBlockRenderer";
import { UserMessageContent } from "@/components/chat/home/UserMessageBubble";
import { useDoctorConversations } from "@/context/DoctorConversationsContext";
import { blockAssociatedValue } from "@/lib/chat/block-normalizer";
import { formatClock } from "@/lib/hospital/labels";
import { doctorMessagePlainText, inferActorType } from "@/lib/hospital/message-text";
import type { DoctorMessageDTO } from "@/types/hospital";
import type { ChatBlockDTO } from "@/types/chat";
import type { HealthResourceReference } from "@/types/medical-resource";
import { HealthResourceDetailDialog } from "@/components/chat/resource/HealthResourceDetailDialog";
import { isSymptomQuestionBlock, symptomCollectionId } from "@/lib/chat/symptom-collection";
import { groupSymptomCollectionBlocks } from "@/lib/chat/symptom-collection";
import { SymptomCollectionSummary } from "@/components/chat/blocks/SymptomCollectionBlock";

type DoctorMessagesVariant = "default" | "consult";

function mergeSymptomCollectionMessages(messages: DoctorMessageDTO[]): DoctorMessageDTO[] {
  const questionsByCollection = new Map<string, ChatBlockDTO[]>();
  const summaryCollectionIds = new Set<string>();
  for (const block of messages.flatMap((message) => message.blocks)) {
    if (block.kind === "symptomCollectionCard") {
      const collectionId = symptomCollectionId(block);
      if (collectionId) summaryCollectionIds.add(collectionId);
      continue;
    }
    if (!isSymptomQuestionBlock(block)) continue;
    const collectionId = symptomCollectionId(block);
    if (!collectionId) continue;
    questionsByCollection.set(collectionId, [...(questionsByCollection.get(collectionId) ?? []), block]);
  }
  return messages.flatMap((message) => {
    const summary = message.blocks.find((block) => block.kind === "symptomCollectionCard");
    if (summary) {
      const collectionId = symptomCollectionId(summary);
      const grouped = collectionId ? questionsByCollection.get(collectionId) ?? [] : [];
      // 医生线上问诊只展示同一张汇总卡。模型正文、工具活动和其他展示块
      // 都不属于采集结果，不能混入医生视图。
      return [{ ...message, blocks: [summary, ...grouped] }];
    }
    const questionBlocks = message.blocks.filter(isSymptomQuestionBlock);
    if (questionBlocks.length) {
      const collectionIds = questionBlocks.map(symptomCollectionId).filter((id): id is string => Boolean(id));
      // 已有汇总卡的消息会吞并各轮问答；此处只保留「仅起始卡、尚无汇总」的采集消息。
      if (collectionIds.length && collectionIds.every((id) => summaryCollectionIds.has(id))) return [];
      return [{ ...message, blocks: questionBlocks }];
    }
    return message.blocks.length || doctorMessagePlainText(message) ? [message] : [];
  });
}

function StructuredMessageBlocks({
  blocks,
  onHealthResourceOpen,
  symptomDoctorPreview = false,
}: {
  blocks: ChatBlockDTO[];
  onHealthResourceOpen?: (reference: HealthResourceReference) => void;
  /** 线上问诊：展示患者待填写的采集题面（与 iOS 起始卡一致）。 */
  symptomDoctorPreview?: boolean;
}) {
  return <>{groupSymptomCollectionBlocks(blocks).map((unit) => unit.type === "block"
    ? <ChatBlockRenderer block={unit.block} key={unit.block.id} onHealthResourceOpen={onHealthResourceOpen} />
    : <SymptomCollectionSummary block={unit.summaryBlock} questionBlocks={unit.questionBlocks} showActiveQuestions={symptomDoctorPreview} key={`symptom-${unit.collectionId}`} />)}</>;
}

function consultationCardBlock(message: DoctorMessageDTO): ChatBlockDTO | null {
  return message.blocks.find((block) => block.kind === "consultationCard") ?? null;
}

function messageText(message: DoctorMessageDTO): string {
  const card = consultationCardBlock(message);
  if (card) {
    const value = blockAssociatedValue(card);
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const complaint = (value as Record<string, unknown>).chief_complaint;
      if (typeof complaint === "string" && complaint.trim()) return complaint.trim();
    }
  }
  return message.blocks
    .map((block) => {
      const value = blockAssociatedValue(block);
      return typeof value === "string" ? value : "";
    })
    .filter(Boolean)
    .join("\n\n");
}

function galleryBlocks(message: DoctorMessageDTO): ChatBlockDTO[] {
  return message.blocks.filter((block) => block.kind === "imageGallery" || block.kind === "fileGallery");
}

function galleryItemCount(blocks: ChatBlockDTO[]): number {
  return blocks.reduce((total, block) => {
    const value = blockAssociatedValue(block);
    return total + (Array.isArray(value) ? value.length : 0);
  }, 0);
}

/** 参考图头像：有头像 URL 用图片，否则用名称首字圆形头像。 */
function ConsultAvatar({ name, avatarUrl, doctor }: { name: string; avatarUrl?: string; doctor?: boolean }) {
  return (
    <span className={`consult-msg__avatar${doctor ? " consult-msg__avatar--doctor" : ""}`} aria-hidden="true">
      {avatarUrl
        // eslint-disable-next-line @next/next/no-img-element
        ? <img src={avatarUrl} alt="" />
        : (name || "患").slice(0, 1)}
    </span>
  );
}

/** DOCTOR-WORKSPACE-000004 页面形态修订：线上问诊参考图气泡（仅线上问诊页使用）。
 *
 * 患者：左侧绿色头像 + “患者 时间” + 白色气泡，附件以“附件（N）+ 缩略图”展示；
 * 医生：右侧头像 + “姓名 · 职称 · 科室 时间” + 浅绿气泡；AI 同理带 AI 标记；
 * 系统消息：居中带盾牌图标的“系统提示”。无文本的系统卡片（医生介绍卡）不渲染。
 */
function ConsultMessage({
  message,
  patientName,
  highlighted,
  ended = false,
  onHealthResourceOpen,
}: {
  message: DoctorMessageDTO;
  patientName?: string;
  highlighted: boolean;
  ended?: boolean;
  onHealthResourceOpen?: (reference: HealthResourceReference) => void;
}) {
  const actor = inferActorType(message);
  const key = message.client_message_id || message.server_message_id || `${message.created_at}-${message.role}`;
  const id = `doctor-msg-${message.client_message_id}`;
  const text = messageText(message) || doctorMessagePlainText(message);

  if (actor === "system") {
    if (!text) return null;
    return (
      <div className={`consult-msg-tip${ended ? " consult-msg-tip--muted" : ""}`} key={key} data-actor="system">
        <ShieldCheck size={13} strokeWidth={2.2} aria-hidden="true" />
        <span>系统提示：{text}</span>
      </div>
    );
  }

  if (actor === "patient") {
    const galleries = galleryBlocks(message);
    const name = patientName || message.sender?.display_name || "患者";
    return (
      <article className={`consult-msg consult-msg--patient${highlighted ? " doctor-message--highlight" : ""}`} key={key} id={id} data-actor="patient">
        <ConsultAvatar name={name} avatarUrl={message.sender?.avatar_url} />
        <div className="consult-msg__main">
          <p className="consult-msg__meta">患者 {formatClock(message.created_at)}</p>
          <div className="consult-msg__bubble">
            {/* 与普通 Chat 使用同一套消息块渲染，报告引用、图片、附件和其他通用卡片均可见。 */}
            <UserMessageContent blocks={message.blocks} attachmentCount={galleries.length ? galleryItemCount(galleries) : undefined} onHealthResourceOpen={onHealthResourceOpen} />
            {!message.blocks.length && text ? <p className="consult-msg__text">{text}</p> : null}
          </div>
        </div>
      </article>
    );
  }

  const isDoctor = actor === "doctor";
  const doctorInfo = message.sender?.doctor;
  const name = isDoctor
    ? (doctorInfo?.display_name || message.sender?.display_name || "医生")
    : (message.sender?.agent?.display_name || message.sender?.display_name || "AI 助手");
  const meta = isDoctor
    ? [name, doctorInfo?.title, doctorInfo?.department_name].filter(Boolean).join(" · ")
    : `${name} · AI`;
  return (
    <article className={`consult-msg consult-msg--doctor${highlighted ? " doctor-message--highlight" : ""}`} key={key} id={id} data-actor={actor}>
      <div className="consult-msg__main">
        <p className="consult-msg__meta">{meta} {formatClock(message.created_at)}</p>
        <div className="consult-msg__bubble">
          {message.blocks.length
            ? <StructuredMessageBlocks blocks={message.blocks} onHealthResourceOpen={onHealthResourceOpen} symptomDoctorPreview />
            : <p className="consult-msg__text">{text}</p>}
        </div>
      </div>
      <ConsultAvatar name={name} avatarUrl={message.sender?.avatar_url} doctor />
    </article>
  );
}

export function DoctorMessageList({
  messages,
  patientName,
  highlightId,
  hasMore = false,
  loadingOlder = false,
  onLoadOlder,
  variant = "default",
  ended = false,
}: {
  messages: DoctorMessageDTO[];
  patientName?: string;
  highlightId?: string | null;
  /** DOCTOR-WORKSPACE-000004 第 34 问：向上加载更早消息。 */
  hasMore?: boolean;
  loadingOlder?: boolean;
  onLoadOlder?: () => void;
  /** 线上问诊页参考图气泡样式；默认保持原工作台样式。 */
  variant?: DoctorMessagesVariant;
  ended?: boolean;
}) {
  const [activeReference, setActiveReference] = useState<HealthResourceReference | null>(null);
  const renderedMessages = mergeSymptomCollectionMessages(messages);
  if (!messages.length) {
    return (
      <div className="empty-state">
        <div className="empty-state__mark"><HeartPulse size={22} /></div>
        <div>
          <p className="empty-state__eyebrow">医生工作台</p>
          <h1>暂无消息</h1>
          <p>该会话还没有可展示的对话记录。</p>
        </div>
      </div>
    );
  }

  if (variant === "consult") {
    return (
      <div className="messages doctor-messages doctor-messages--consult" aria-live="polite">
        {hasMore ? (
          <div className="doctor-messages__older">
            <button type="button" className="doctor-button doctor-button--ghost" disabled={loadingOlder} onClick={() => onLoadOlder?.()}>
              {loadingOlder ? "正在加载更早消息…" : "加载更早消息"}
            </button>
          </div>
        ) : null}
        {renderedMessages.map((message) => (
          <ConsultMessage
            key={message.client_message_id || message.server_message_id || `${message.created_at}-${message.role}`}
            message={message}
            patientName={patientName}
            highlighted={highlightId === message.client_message_id || highlightId === message.server_message_id}
            ended={ended}
            onHealthResourceOpen={setActiveReference}
          />
        ))}
        <HealthResourceDetailDialog reference={activeReference} onClose={() => setActiveReference(null)} />
      </div>
    );
  }

  return (
    <div className="messages doctor-messages" aria-live="polite">
      {hasMore ? (
        <div className="doctor-messages__older">
          <button type="button" className="doctor-button doctor-button--ghost" disabled={loadingOlder} onClick={() => onLoadOlder?.()}>
            {loadingOlder ? "正在加载更早消息…" : "加载更早消息"}
          </button>
        </div>
      ) : null}
      {renderedMessages.map((message) => {
        const actor = inferActorType(message);
        const highlighted = highlightId === message.client_message_id || highlightId === message.server_message_id;
        const key = message.client_message_id || message.server_message_id || `${message.created_at}-${message.role}`;
        if (actor === "system") {
          return (
            <div className="doctor-system-event" key={key} data-actor="system">
              <span>{doctorMessagePlainText(message) || "系统事件"} · {formatClock(message.created_at)}</span>
            </div>
          );
        }
        if (actor === "patient") {
          return (
            <article className={`message message--user doctor-message${highlighted ? " doctor-message--highlight" : ""}`} key={key} id={`doctor-msg-${message.client_message_id}`} data-actor="patient">
              <div className="message__content">
                <p className="doctor-message__meta">患者 · {patientName || message.sender?.display_name || "患者"} · {formatClock(message.created_at)}</p>
                {/* 与主 chat 用户消息共用同一套渲染：imageGallery 图片可见（CHAT-WEB-029） */}
                <UserMessageContent blocks={message.blocks} onHealthResourceOpen={setActiveReference} />
              </div>
            </article>
          );
        }
        const isDoctor = actor === "doctor";
        const name = isDoctor
          ? (message.sender?.doctor?.display_name || message.sender?.display_name || "医生")
          : (message.sender?.agent?.display_name || message.sender?.display_name || "AI 助手");
        const title = isDoctor ? message.sender?.doctor?.title : "";
        return (
          <article className={`message message--assistant doctor-message${highlighted ? " doctor-message--highlight" : ""}`} key={key} id={`doctor-msg-${message.client_message_id}`} data-actor={actor}>
            <div className="message__content">
              <p className="doctor-message__meta">
                <span className={`doctor-actor-tag doctor-actor-tag--${actor}`}>{isDoctor ? "真人医生" : "AI"}</span>
                {name}{title ? ` · ${title}` : ""} · {formatClock(message.created_at)}
              </p>
              <div className="message__body">
                {message.blocks.length
                  ? <StructuredMessageBlocks blocks={message.blocks} onHealthResourceOpen={setActiveReference} />
                  : <p>{doctorMessagePlainText(message)}</p>}
              </div>
            </div>
          </article>
        );
      })}
      <HealthResourceDetailDialog reference={activeReference} onClose={() => setActiveReference(null)} />
    </div>
  );
}

export function DoctorMessages({
  highlightId,
  variant = "default",
  ended = false,
}: {
  highlightId?: string | null;
  variant?: DoctorMessagesVariant;
  ended?: boolean;
}) {
  const conversations = useDoctorConversations();
  if (conversations.detailStatus === "loading" && !conversations.messages.length) {
    return <div className="empty-state" aria-busy="true"><p>正在加载对话…</p></div>;
  }
  if (conversations.detailStatus === "error") {
    return (
      <div className="empty-state" role="alert">
        <h1>会话加载失败</h1>
        <p>{conversations.detailError || "请稍后重试。"}</p>
        <button type="button" className="doctor-button" onClick={() => void conversations.reloadSelected()}>重新加载</button>
      </div>
    );
  }
  return (
    <DoctorMessageList
      messages={conversations.messages}
      patientName={conversations.detail?.patient_display_name}
      highlightId={highlightId}
      hasMore={conversations.hasMoreMessages}
      loadingOlder={conversations.loadingOlder}
      onLoadOlder={() => void conversations.loadOlderMessages()}
      variant={variant}
      ended={ended}
    />
  );
}
