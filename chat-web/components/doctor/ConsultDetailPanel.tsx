"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";
import { DoctorComposer } from "@/components/doctor/DoctorComposer";
import { DoctorMessages } from "@/components/doctor/DoctorMessages";
import { useOptionalDoctorConversations } from "@/context/DoctorConversationsContext";
import { useDoctorMessageFollow } from "@/hooks/useDoctorMessageFollow";
import { END_REASON_OPTIONS, SERVICE_STATUS_LABEL, endReasonLabel } from "@/lib/hospital/labels";
import type { ConversationEndReasonCode } from "@/types/hospital";

/** 接管二次确认条（待接诊/AI 服务中）。 */
function TakeoverBar() {
  const conversations = useOptionalDoctorConversations();
  const [pending, setPending] = useState(false);
  const detail = conversations?.detail ?? null;
  const status = detail?.service_status ?? null;
  const busy = conversations?.writeBusy ?? false;

  useEffect(() => { setPending(false); }, [detail?.thread_id, status]);
  if (!conversations || !detail) return null;
  if (status !== "ai_active" && status !== "pending_doctor") return null;

  return (
    <div className="patient-drawer__takeover">
      <span className={`doctor-tag doctor-tag--outline doctor-tag--status-${status}`}>{SERVICE_STATUS_LABEL[status]}</span>
      <span className="patient-drawer__takeover-spacer" />
      {!pending ? (
        <button type="button" className="doctor-button patient-button-inline" disabled={busy} onClick={() => setPending(true)}>接管问诊</button>
      ) : (
        <div className="patient-drawer__confirm" role="alertdialog" aria-label="确认接管问诊">
          <p>接管后由医生亲自回复该患者。确认接管？</p>
          <button
            type="button"
            className="doctor-button patient-button-inline"
            disabled={busy}
            onClick={() => void conversations.join().then((ok) => { if (ok) setPending(false); })}
          >
            {busy ? "处理中…" : "确认接管"}
          </button>
          <button type="button" className="doctor-button doctor-button--ghost patient-button-inline" disabled={busy} onClick={() => setPending(false)}>返回</button>
        </div>
      )}
    </div>
  );
}

/** 结束问诊：头部红色按钮 + 固定枚举表单（第 28 问）。 */
function EndConversationSection() {
  const conversations = useOptionalDoctorConversations();
  const detail = conversations?.detail ?? null;
  const [ending, setEnding] = useState(false);
  const [endReason, setEndReason] = useState<ConversationEndReasonCode>("resolved");
  const [endNote, setEndNote] = useState("");

  useEffect(() => { setEnding(false); }, [detail?.thread_id]);
  if (!conversations || !detail) return null;
  const ended = detail.service_status === "ended";
  const busy = conversations.writeBusy;
  const reasonText = endReasonLabel(detail);

  if (ended) {
    return <span className="consult-detail__ended">已结束{reasonText ? `：${reasonText}` : ""}</span>;
  }
  if (!ending) {
    return (
      <button type="button" className="doctor-button doctor-button--danger-outline patient-button-inline" disabled={busy} onClick={() => setEnding(true)}>
        结束问诊
      </button>
    );
  }
  return (
    <form
      className="doctor-end-form consult-end-form"
      onSubmit={(event) => {
        event.preventDefault();
        void conversations.endConversation(endReason, endNote.trim() || undefined).then((ok) => { if (ok) setEnding(false); });
      }}
    >
      <fieldset>
        <legend>结束原因（必填）</legend>
        {END_REASON_OPTIONS.map((option) => (
          <label key={option.value}>
            <input type="radio" name="consult-end-reason" checked={endReason === option.value} onChange={() => setEndReason(option.value)} />
            {option.label}
          </label>
        ))}
      </fieldset>
      <textarea
        value={endNote}
        onChange={(event) => setEndNote(event.target.value)}
        placeholder={endReason === "other" ? "补充说明（选择“其他”时必填）" : "补充说明（可选）"}
        aria-label="结束补充说明"
      />
      <div className="doctor-end-form__footer">
        <button type="button" className="doctor-button doctor-button--ghost patient-button-inline" onClick={() => setEnding(false)}>取消</button>
        <button type="submit" className="doctor-button doctor-button--danger patient-button-inline" disabled={busy || (endReason === "other" && !endNote.trim())}>确认结束</button>
      </div>
    </form>
  );
}

/** 独立线上问诊：消息与回复区（资料与记录在 activity 侧栏）。 */
export function ConsultDetailPanel() {
  const conversations = useOptionalDoctorConversations();
  const detail = conversations?.detail ?? null;
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const follow = useDoctorMessageFollow(scrollRef, conversations?.messages ?? [], conversations?.selectedThreadId ?? null);

  if (!conversations || !detail) return null;
  const status = detail.service_status;
  const ended = status === "ended";

  return (
    <aside
      className={`patient-aside patient-aside--drawer consult-detail${ended ? " consult-detail--ended" : ""}`}
      aria-label="问诊详情"
    >
      <header className="patient-drawer__head consult-detail__head">
        <div className="consult-detail__title-group">
          <h2>问诊详情</h2>
          {detail.consult_no ? <span className="consult-detail__consult-no">{detail.consult_no}</span> : null}
        </div>
        <div className="consult-detail__head-actions">
          <span className={`doctor-tag doctor-tag--outline doctor-tag--status-${status}`}>{SERVICE_STATUS_LABEL[status]}</span>
          <EndConversationSection />
        </div>
      </header>

      <div className="consult-detail__scroll">
        <TakeoverBar />
        <div className="doctor-scroll-frame patient-drawer__scroll consult-detail__messages">
          <div className="chat-scroll" data-chat-scroll-root ref={scrollRef}>
            <section className="message-column patient-drawer__messages">
              <DoctorMessages variant="consult" ended={ended} />
            </section>
          </div>
          {follow.showNewMessages && (
            <button type="button" className="doctor-new-messages" onClick={follow.jumpToLatest}>
              <ArrowDown size={13} strokeWidth={2.2} />
              有 {follow.unseenCount} 条新消息
            </button>
          )}
        </div>
      </div>

      <div className="composer-wrap patient-drawer__composer consult-detail__composer"><DoctorComposer consultAssistEnabled /></div>
    </aside>
  );
}
