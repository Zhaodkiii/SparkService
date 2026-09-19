"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useEffect, useRef, useState } from "react";
import { ArrowDown, MessageSquarePlus, X } from "lucide-react";
import { DoctorComposer } from "@/components/doctor/DoctorComposer";
import { DoctorMessages } from "@/components/doctor/DoctorMessages";
import { useOptionalDoctorConversations } from "@/context/DoctorConversationsContext";
import { usePatientWorkspace } from "@/context/PatientWorkspaceContext";
import { useDoctorMessageFollow } from "@/hooks/useDoctorMessageFollow";
import {
  END_REASON_OPTIONS,
  GENDER_LABEL,
  SERVICE_STATUS_LABEL,
  patientListTime,
  relativeTime,
} from "@/lib/hospital/labels";
import type { ConversationEndReasonCode } from "@/types/hospital";

/** D-016：接管/取消接管二次确认条。 */
function TakeoverConfirmBar() {
  const conversations = useOptionalDoctorConversations();
  const [pending, setPending] = useState<"join" | "leave" | null>(null);
  const detail = conversations?.detail ?? null;
  const status = detail?.service_status ?? null;
  const busy = conversations?.writeBusy ?? false;

  useEffect(() => { setPending(null); }, [detail?.thread_id, status]);
  if (!conversations || !detail) return null;

  const confirm = async () => {
    const ok = pending === "join" ? await conversations.join() : await conversations.leave();
    if (ok) setPending(null);
  };

  return (
    <div className="patient-drawer__takeover">
      <span className={`doctor-tag doctor-tag--status-${status}`}>{status ? SERVICE_STATUS_LABEL[status] : "状态未知"}</span>
      <span className="patient-drawer__takeover-spacer" />
      {(status === "ai_active" || status === "pending_doctor") && pending !== "join" && (
        <button type="button" className="doctor-button patient-button-inline" disabled={busy} onClick={() => setPending("join")}>接管会话</button>
      )}
      {status === "doctor_joined" && pending !== "leave" && (
        <button type="button" className="doctor-button doctor-button--ghost patient-button-inline" disabled={busy} onClick={() => setPending("leave")}>取消接管</button>
      )}
      {pending && (
        <div className="patient-drawer__confirm" role="alertdialog" aria-label={pending === "join" ? "确认接管会话" : "确认取消接管"}>
          <p>{pending === "join" ? "接管后将暂停 AI 自动回复，由医生回复。确认接管？" : "取消接管后 AI 将恢复自动回复。确认取消？"}</p>
          <button type="button" className="doctor-button patient-button-inline" disabled={busy} onClick={() => void confirm()}>
            {busy ? "处理中…" : pending === "join" ? "确认接管" : "确认取消接管"}
          </button>
          <button type="button" className="doctor-button doctor-button--ghost patient-button-inline" disabled={busy} onClick={() => setPending(null)}>返回</button>
        </div>
      )}
    </div>
  );
}

/** D-015：医生操作区——结束会话（服务端成功响应为准）。 */
function DrawerOperations() {
  const conversations = useOptionalDoctorConversations();
  const detail = conversations?.detail ?? null;
  const [ending, setEnding] = useState(false);
  const [endReason, setEndReason] = useState<ConversationEndReasonCode>("resolved");
  const [endNote, setEndNote] = useState("");

  useEffect(() => {
    if (!detail) return;
    setEnding(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.thread_id]);

  if (!conversations || !detail) return null;
  const ended = detail.service_status === "ended";
  const busy = conversations.writeBusy;

  return (
    <details className="patient-drawer__ops">
      <summary>结束会话</summary>
      <div className="patient-drawer__ops-body">
        {ended ? (
          <p className="patient-module__hint">本次对话已结束{detail.end_reason ? `：${detail.end_reason}` : ""}，历史消息仍可查看。</p>
        ) : !ending ? (
          <button type="button" className="doctor-button doctor-button--danger patient-button-inline" disabled={busy} onClick={() => setEnding(true)}>结束本次对话</button>
        ) : (
          <form
            className="doctor-end-form"
            onSubmit={(event) => {
              event.preventDefault();
              void conversations.endConversation(endReason, endNote.trim() || undefined).then((ok) => { if (ok) setEnding(false); });
            }}
          >
            <fieldset>
              <legend>结束原因</legend>
              {END_REASON_OPTIONS.map((option) => (
                <label key={option.value}>
                  <input type="radio" name="drawer-end-reason" checked={endReason === option.value} onChange={() => setEndReason(option.value)} />
                  {option.label}
                </label>
              ))}
            </fieldset>
            <textarea value={endNote} onChange={(event) => setEndNote(event.target.value)} placeholder={endReason === "other" ? "补充说明（选择“其他”时必填）" : "补充说明（可选）"} aria-label="结束补充说明" />
            <div className="doctor-end-form__footer">
              <button type="button" className="doctor-button doctor-button--ghost patient-button-inline" onClick={() => setEnding(false)}>取消</button>
              <button type="submit" className="doctor-button doctor-button--danger patient-button-inline" disabled={busy || (endReason === "other" && !endNote.trim())}>确认结束</button>
            </div>
          </form>
        )}
      </div>
    </details>
  );
}

/** D-002/D-014：右侧会话抽屉——复用现有消息流与输入区，只承载当前会话。 */
function PatientConversationDrawer() {
  const conversations = useOptionalDoctorConversations();
  const workspace = usePatientWorkspace();
  const detail = conversations?.detail ?? null;
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const follow = useDoctorMessageFollow(scrollRef, conversations?.messages ?? [], conversations?.selectedThreadId ?? null);

  return (
    <aside className="patient-aside patient-aside--drawer" aria-label="会话详情">
      <header className="patient-drawer__head">
        <div>
          <h2>{detail ? `${detail.patient_display_name || "患者"} · ${detail.agent.name}` : "会话详情"}</h2>
          {detail && (
            <p>
              {detail.hospital.short_name || detail.hospital.name} · {detail.department.short_name || detail.department.name}
              {detail.doctor_joined_at ? ` · 接管于 ${relativeTime(detail.doctor_joined_at)}` : ""}
            </p>
          )}
        </div>
        <button className="icon-button" type="button" aria-label="关闭会话抽屉" onClick={() => conversations?.selectConversation(null)}><X size={17} /></button>
      </header>
      <TakeoverConfirmBar />
      <div className="doctor-scroll-frame patient-drawer__scroll">
        <div className="chat-scroll" data-chat-scroll-root ref={scrollRef}>
          <section className="message-column patient-drawer__messages">
            <DoctorMessages />
          </section>
        </div>
        {follow.showNewMessages && (
          <button type="button" className="doctor-new-messages" onClick={follow.jumpToLatest}>
            <ArrowDown size={13} strokeWidth={2.2} />
            有 {follow.unseenCount} 条新消息
          </button>
        )}
      </div>
      <DrawerOperations />
      <div className="composer-wrap patient-drawer__composer"><DoctorComposer /></div>
      {detail?.service_status === "ended" && (
        <div className="patient-drawer__new">
          <button
            type="button"
            className="doctor-button patient-button-primary"
            disabled={workspace.actionBusy}
            onClick={() => void workspace.createConversation()}
          >
            <MessageSquarePlus size={14} strokeWidth={2.2} />新建对话
          </button>
          {workspace.actionError && <p className="patient-module__error" role="alert">{workspace.actionError}</p>}
        </div>
      )}
    </aside>
  );
}

/** 原型（未打开会话详情）：右侧展示患者辅助信息——患者画像、会话时间线。 */
function PatientAuxPanel() {
  const workspace = usePatientWorkspace();
  const conversationsCtx = useOptionalDoctorConversations();
  const profile = workspace.profile.data;
  const conversations = workspace.conversations.data ?? [];

  return (
    <aside className="patient-aside patient-aside--aux" aria-label="患者辅助信息">
      <header className="patient-aside__head">
        <h2>患者辅助信息</h2>
        <span>未打开会话</span>
      </header>
      <div className="patient-aside__scroll">
        <section className="patient-aux-card">
          <h3>患者画像</h3>
          <p>性别　{profile ? (GENDER_LABEL[profile.patient.gender] ?? "未填写") : "—"}</p>
          <p>年龄　{profile?.patient.age !== null && profile ? `${profile.patient.age}岁` : "—"}</p>
          <p>会话数　{conversations.length} 条</p>
          <p>重点患者　{profile?.work_flags.priority_patient ? "是" : "否"}</p>
        </section>
        <section className="patient-aux-card">
          <h3>会话时间线</h3>
          {conversations.length === 0 && <p className="patient-aux-card__meta">暂无会话。</p>}
          <ul className="patient-timeline">
            {conversations.slice(0, 6).map((card) => (
              <li key={card.thread_id}>
                <button type="button" onClick={() => conversationsCtx?.selectConversation(card.thread_id)}>
                  <i aria-hidden="true" />
                  <span>{patientListTime(card.updated_at)}　{card.agent.name} · {SERVICE_STATUS_LABEL[card.service_status]}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </aside>
  );
}

/** D-011/D-028：右侧区域——打开会话时为会话抽屉，否则为患者辅助信息。 */
export function PatientAsidePanel() {
  const conversations = useOptionalDoctorConversations();
  if (conversations?.selectedThreadId) return <PatientConversationDrawer />;
  return <PatientAuxPanel />;
}
