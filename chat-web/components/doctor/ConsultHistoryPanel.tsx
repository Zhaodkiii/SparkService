"use client";

import { ChevronRight, Star, X } from "lucide-react";
import { useOptionalDoctorConversations } from "@/context/DoctorConversationsContext";
import { SERVICE_STATUS_LABEL, patientListTime } from "@/lib/hospital/labels";
import type { ConsultRecordDTO } from "@/types/hospital";

function ConsultRecordRow({
  card,
  open,
  fresh,
  onOpen,
}: {
  card: ConsultRecordDTO;
  open: boolean;
  fresh: boolean;
  onOpen: () => void;
}) {
  const unread = card.unread_count ?? 0;
  return (
    <li>
      <button type="button" className="patient-conversation-row consult-record" aria-current={open ? "true" : undefined} onClick={onOpen}>
        <span className="consult-record__time">{patientListTime(card.updated_at)}</span>
        <span className="consult-record__body">
          <span className="patient-conversation-row__title">
            <i className="consult-record__dot" aria-hidden="true" />
            {card.title || card.agent.name}
            <em className="consult-record__independent">独立问诊</em>
            {fresh && <i className="doctor-card__fresh" role="img" aria-label="新消息" title="新消息" />}
            {unread > 0 && <b className="doctor-card__unread" aria-label={`${unread} 条未读`}>{unread > 99 ? "99+" : unread}</b>}
          </span>
          <span className="consult-record__no">问诊编号：{card.consult_no}</span>
          {card.first_patient_message_excerpt ? (
            <span className="consult-record__excerpt">患者首句：{card.first_patient_message_excerpt}</span>
          ) : null}
          <span className="patient-conversation-row__tags">
            <span className="patient-conversation-row__attachments">附件：{card.attachment_count ?? 0} 个</span>
            {card.doctor_replied ? <span className="consult-record__replied">医生已回复</span> : null}
            {card.doctor_attention_level === "priority" && (
              <em className="patient-card__priority"><Star size={11} strokeWidth={2.4} />重点</em>
            )}
          </span>
        </span>
        <span className={`doctor-tag doctor-tag--status-${card.service_status}`}>{SERVICE_STATUS_LABEL[card.service_status]}</span>
        <ChevronRight size={15} className="patient-conversation-row__chevron" aria-hidden="true" />
      </button>
    </li>
  );
}

/** 线上问诊历史：复用项目通用 activity-panel 侧栏，默认由父级控制收起。 */
export function ConsultHistoryPanel({
  open,
  onClose,
  records,
  status,
  error,
  onRetry,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  records: ConsultRecordDTO[];
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
  onRetry: () => void;
  onSelect: (threadId: string) => void;
}) {
  const conversations = useOptionalDoctorConversations();
  const selectedThreadId = conversations?.selectedThreadId ?? null;

  return (
    <aside
      className={`activity-panel consult-history-panel${open ? " activity-panel--open" : ""}`}
      aria-hidden={!open}
      aria-label="线上问诊记录"
    >
      <header>
        <div>
          <p>线上问诊记录</p>
          <span>每次问诊为独立对话 · 共 {records.length} 条</span>
        </div>
        <button className="icon-button" type="button" aria-label="关闭问诊记录" onClick={onClose}>
          <X size={17} />
        </button>
      </header>
      <div className="activity-panel__body consult-history-panel__body">
        {error ? (
          <p className="patient-module__error" role="alert">
            {error}
            <button type="button" className="doctor-inline-retry" onClick={onRetry}>重试</button>
          </p>
        ) : null}
        {status === "loading" && records.length === 0 ? (
          <p className="patient-module__hint">正在加载问诊记录…</p>
        ) : null}
        {status === "ready" && records.length === 0 && !error ? (
          <p className="patient-module__hint">该患者还没有由客户端发起的线上问诊。</p>
        ) : null}
        {records.length > 0 ? (
          <ul className="patient-conversation-list consult-history-panel__list">
            {records.map((card) => (
              <ConsultRecordRow
                key={card.thread_id}
                card={card}
                open={selectedThreadId === card.thread_id}
                fresh={selectedThreadId !== card.thread_id && (conversations?.newMessageThreadIds.includes(card.thread_id) ?? false)}
                onOpen={() => {
                  onSelect(card.thread_id);
                  onClose();
                }}
              />
            ))}
          </ul>
        ) : null}
      </div>
    </aside>
  );
}
