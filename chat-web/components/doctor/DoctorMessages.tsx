"use client";

import { HeartPulse } from "lucide-react";
import { ChatBlockRenderer } from "@/components/chat/home/ChatBlockRenderer";
import { useDoctorConversations } from "@/context/DoctorConversationsContext";
import { formatClock } from "@/lib/hospital/labels";
import { doctorMessagePlainText, inferActorType } from "@/lib/hospital/message-text";
import type { DoctorMessageDTO } from "@/types/hospital";

export function DoctorMessageList({
  messages,
  patientName,
  highlightId,
}: {
  messages: DoctorMessageDTO[];
  patientName?: string;
  highlightId?: string | null;
}) {
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

  return (
    <div className="messages doctor-messages" aria-live="polite">
      {messages.map((message) => {
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
                <div className="message__body">{doctorMessagePlainText(message)}</div>
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
                  ? message.blocks.map((block) => <ChatBlockRenderer block={block} key={block.id} />)
                  : <p>{doctorMessagePlainText(message)}</p>}
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}

export function DoctorMessages({ highlightId }: { highlightId?: string | null }) {
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
  return <DoctorMessageList messages={conversations.messages} patientName={conversations.detail?.patient_display_name} highlightId={highlightId} />;
}
