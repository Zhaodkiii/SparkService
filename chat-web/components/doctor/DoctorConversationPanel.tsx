"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useDoctorConversations } from "@/context/DoctorConversationsContext";
import { ATTENTION_LABEL, END_REASON_OPTIONS, RISK_LABEL, SERVICE_STATUS_LABEL, relativeTime } from "@/lib/hospital/labels";
import { firstRiskMessageId } from "@/lib/hospital/message-text";
import type { DoctorAttentionLevel } from "@/types/hospital";

const ATTENTION_OPTIONS: DoctorAttentionLevel[] = ["normal", "follow_up", "priority"];

export function DoctorConversationPanel({ open, onClose, onJumpToRisk }: { open: boolean; onClose: () => void; onJumpToRisk?: (messageId: string) => void }) {
  const conversations = useDoctorConversations();
  const detail = conversations.detail;
  const [level, setLevel] = useState<DoctorAttentionLevel>("normal");
  const [note, setNote] = useState("");
  const [ending, setEnding] = useState(false);
  const [endReason, setEndReason] = useState<(typeof END_REASON_OPTIONS)[number]["value"]>("已完成咨询");
  const [endNote, setEndNote] = useState("");

  useEffect(() => {
    if (!detail) return;
    setLevel(detail.doctor_attention_level);
    setNote(detail.attention_note ?? "");
    setEnding(false);
    // Reset local form only when switching conversations.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.thread_id]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const riskMessageId = firstRiskMessageId(conversations.messages);
  const ended = detail?.service_status === "ended";

  return (
    <aside className={`activity-panel${open ? " activity-panel--open" : ""}`} aria-hidden={!open} aria-label="患者资料与本次服务">
      <header>
        <div>
          <p>患者与本次服务</p>
          <span>{detail ? `${detail.patient_display_name} · ${detail.department.name}` : "未选择会话"}</span>
        </div>
        <button className="icon-button" type="button" aria-label="关闭患者资料" onClick={onClose}><X size={17} /></button>
      </header>
      {detail && (
        <div className="activity-panel__body doctor-panel-body">
          <section className="doctor-panel-section">
            <h2>服务状态</h2>
            <p><strong>{SERVICE_STATUS_LABEL[detail.service_status]}</strong></p>
            <p className="doctor-panel-muted">
              {detail.doctor_joined_at ? `接管于 ${relativeTime(detail.doctor_joined_at)}` : `分配于 ${relativeTime(detail.assigned_at)}`}
              {detail.ended_at ? ` · 结束于 ${relativeTime(detail.ended_at)}` : ""}
            </p>
            {detail.end_reason ? <p className="doctor-panel-muted">结束原因：{detail.end_reason}</p> : null}
          </section>
          <section className="doctor-panel-section">
            <h2>医生关注</h2>
            <div className="doctor-radio-list">
              {ATTENTION_OPTIONS.map((item) => (
                <label key={item}>
                  <input type="radio" name="doctor-attention" checked={level === item} disabled={ended || conversations.writeBusy} onChange={() => setLevel(item)} />
                  {ATTENTION_LABEL[item]}
                </label>
              ))}
            </div>
            <textarea value={note} disabled={ended || conversations.writeBusy} onChange={(event) => setNote(event.target.value)} placeholder="内部备注（仅医生可见）" aria-label="关注备注" />
            <button type="button" className="doctor-button" disabled={ended || conversations.writeBusy} onClick={() => void conversations.updateAttention(level, note)}>保存关注设置</button>
          </section>
          <section className="doctor-panel-section">
            <h2>AI 风险摘要</h2>
            <p><strong>{RISK_LABEL[detail.risk_signal_level]}</strong></p>
            <p className="doctor-panel-muted">风险等级与医生关注是两套独立标签。</p>
            <button
              type="button"
              className="doctor-button doctor-button--ghost"
              disabled={!riskMessageId}
              onClick={() => riskMessageId && onJumpToRisk?.(riskMessageId)}
            >
              定位到原风险消息
            </button>
          </section>
          <section className="doctor-panel-section">
            <h2>患者授权摘要</h2>
            <ul className="doctor-consent-list">
              <li>显示名：{detail.patient_display_name}</li>
              <li>科室：{detail.department.name}</li>
              <li>医院：{detail.hospital.name}</li>
              {detail.member_id ? <li>成员编号已授权（{detail.member_id}）</li> : <li>未关联成员档案</li>}
            </ul>
          </section>
          <section className="doctor-panel-section doctor-panel-end">
            <h2>本次服务</h2>
            {ended ? (
              <p className="doctor-panel-muted">本次对话已结束，历史消息仍保留。</p>
            ) : !ending ? (
              <button type="button" className="doctor-button doctor-button--danger" disabled={conversations.writeBusy} onClick={() => setEnding(true)}>结束本次对话</button>
            ) : (
              <form
                className="doctor-end-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  const reason = endReason === "其他" && endNote.trim() ? `${endReason}：${endNote.trim()}` : endNote.trim() ? `${endReason}：${endNote.trim()}` : endReason;
                  void conversations.endConversation(reason).then((ok) => { if (ok) setEnding(false); });
                }}
              >
                <p>结束后双方仍可查看历史消息，医生不能继续回复；不会删除会话记录。</p>
                <fieldset>
                  <legend>结束原因</legend>
                  {END_REASON_OPTIONS.map((option) => (
                    <label key={option.value}>
                      <input type="radio" name="end-reason" checked={endReason === option.value} onChange={() => setEndReason(option.value)} />
                      {option.label}
                    </label>
                  ))}
                </fieldset>
                <textarea value={endNote} onChange={(event) => setEndNote(event.target.value)} placeholder="补充说明（可选）" aria-label="结束补充说明" />
                <div className="doctor-end-form__footer">
                  <button type="button" className="doctor-button doctor-button--ghost" onClick={() => setEnding(false)}>取消</button>
                  <button type="submit" className="doctor-button doctor-button--danger" disabled={conversations.writeBusy}>确认结束</button>
                </div>
              </form>
            )}
          </section>
          {conversations.writeError ? <p className="doctor-panel-error" role="alert">{conversations.writeError}</p> : null}
        </div>
      )}
    </aside>
  );
}
