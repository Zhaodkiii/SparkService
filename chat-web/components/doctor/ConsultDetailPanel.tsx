"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, Download, Eye, FileText, Image as ImageIcon, Star } from "lucide-react";
import { ConversationRiskPanel } from "@/components/doctor/ConversationRiskPanel";
import { DoctorComposer } from "@/components/doctor/DoctorComposer";
import { DoctorMessages } from "@/components/doctor/DoctorMessages";
import { useOptionalAuth } from "@/context/AuthContext";
import { useOptionalDoctorConversations } from "@/context/DoctorConversationsContext";
import { useDoctorMessageFollow } from "@/hooks/useDoctorMessageFollow";
import { SparkHospitalApi } from "@/lib/api/hospital-api";
import { hospitalErrorMessage, newIdempotencyKey } from "@/lib/hospital/errors";
import { formatFileSize } from "@/lib/hospital/attachments";
import {
  ATTENTION_LABEL,
  END_REASON_OPTIONS,
  GENDER_LABEL,
  RISK_LABEL,
  SERVICE_STATUS_LABEL,
  endReasonLabel,
  formatClock,
  patientListTime,
  relativeTime,
} from "@/lib/hospital/labels";
import type {
  ConversationAttachmentItemDTO,
  ConversationEndReasonCode,
  DoctorAttentionLevel,
  PatientSummaryDTO,
  PatientWorkspaceDTO,
} from "@/types/hospital";

const ATTENTION_OPTIONS: DoctorAttentionLevel[] = ["normal", "follow_up", "priority"];

function ProfileItem({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <p className="consult-profile__item">
      <span>{label}</span>
      <em>{value === null || value === undefined || value === "" ? "未填写" : value}</em>
    </p>
  );
}

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
      <span className={`doctor-tag doctor-tag--status-${status}`}>{SERVICE_STATUS_LABEL[status]}</span>
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
      <button type="button" className="doctor-button doctor-button--danger patient-button-inline" disabled={busy} onClick={() => setEnding(true)}>
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

/** 患者基础资料（只读，第 11/27 问）。 */
function PatientProfileCard({ profile }: { profile: PatientWorkspaceDTO | null }) {
  const conversations = useOptionalDoctorConversations();
  const doctorName = conversations?.detail?.doctor?.display_name;
  if (!profile) return null;
  const { patient, basic_profile: basic, health_profile: health, medical_safety: safety } = profile;
  return (
    <section className="consult-card" aria-label="患者基础资料">
      <header className="consult-card__head"><h3>患者基础资料（只读）</h3></header>
      <div className="consult-profile__grid">
        <ProfileItem label="姓名" value={patient.display_name} />
        <ProfileItem label="性别" value={GENDER_LABEL[patient.gender] ?? "未填写"} />
        <ProfileItem label="年龄" value={patient.age !== null ? `${patient.age} 岁` : null} />
        <ProfileItem label="身高" value={health.height_cm !== null ? `${health.height_cm} cm` : null} />
        <ProfileItem label="体重" value={health.weight_kg !== null ? `${health.weight_kg} kg` : null} />
        <ProfileItem label="BMI" value={health.bmi !== null ? String(health.bmi) : null} />
        <ProfileItem label="已接诊医生" value={doctorName ?? null} />
        <ProfileItem label="手机" value={basic.phone ?? basic.phone_masked} />
        <ProfileItem label="过敏史" value={safety.allergies.length ? safety.allergies.join("、") : "无"} />
        <ProfileItem label="慢性病史" value={safety.past_medical_history.length ? safety.past_medical_history.join("、") : "无"} />
      </div>
    </section>
  );
}

/** 病历与附件（只读清单，第 11 问）。 */
function AttachmentsCard({ items }: { items: ConversationAttachmentItemDTO[] | null }) {
  const [expanded, setExpanded] = useState(false);
  if (!items) return null;
  const visible = expanded ? items : items.slice(0, 3);
  return (
    <section className="consult-card" aria-label="病历与附件">
      <header className="consult-card__head">
        <h3>病历与附件</h3>
        <span>共 {items.length} 个</span>
      </header>
      {items.length === 0 ? <p className="patient-module__hint">本次问诊暂无附件。</p> : (
        <ul className="consult-attachment-list">
          {visible.map((item, index) => (
            <li key={`${item.file_id ?? index}-${index}`}>
              {item.kind === "image" ? <ImageIcon size={15} /> : <FileText size={15} />}
              <span className="consult-attachment-list__name">
                <strong>{item.filename}</strong>
                <em>{[item.created_at ? patientListTime(item.created_at) : "", formatFileSize(item.file_size ?? 0)].filter(Boolean).join(" · ")}</em>
              </span>
              {item.url ? (
                <>
                  <a href={item.url} target="_blank" rel="noreferrer noopener" aria-label={`预览 ${item.filename}`}><Eye size={14} /></a>
                  <a href={item.url} download aria-label={`下载 ${item.filename}`}><Download size={14} /></a>
                </>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {items.length > 3 ? (
        <button type="button" className="patient-aux-link" onClick={() => setExpanded((current) => !current)}>
          {expanded ? "收起附件" : `查看全部附件（${items.length}）`}
        </button>
      ) : null}
    </section>
  );
}

/** 医生关注设置（第 23 问）。 */
function AttentionSection() {
  const conversations = useOptionalDoctorConversations();
  const detail = conversations?.detail ?? null;
  const [level, setLevel] = useState<DoctorAttentionLevel>("normal");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!detail) return;
    setLevel(detail.doctor_attention_level);
    setNote(detail.attention_note ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.thread_id]);
  if (!conversations || !detail) return null;
  const ended = detail.service_status === "ended";
  const busy = conversations.writeBusy;

  return (
    <details className="patient-drawer__ops">
      <summary>重点关注（仅本人可见）</summary>
      <div className="patient-drawer__ops-body">
        <div className="doctor-radio-list">
          {ATTENTION_OPTIONS.map((item) => (
            <label key={item}>
              <input type="radio" name="consult-attention" checked={level === item} disabled={ended || busy} onChange={() => setLevel(item)} />
              {ATTENTION_LABEL[item]}
            </label>
          ))}
        </div>
        <textarea value={note} disabled={ended || busy} onChange={(event) => setNote(event.target.value)} placeholder="内部备注（仅医生可见）" aria-label="关注备注" />
        <button type="button" className="doctor-button doctor-button--ghost patient-button-inline" disabled={ended || busy} onClick={() => void conversations.updateAttention(level, note)}>保存关注设置</button>
      </div>
    </details>
  );
}

/** 底部 AI 辅助摘要（复用患者工作台总结能力，只读 + 主动生成）。 */
function SummaryCard({ memberId, summary, onGenerated }: { memberId: number; summary: PatientSummaryDTO | null; onGenerated: (value: PatientSummaryDTO) => void }) {
  const auth = useOptionalAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!auth) return null;
  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      const api = new SparkHospitalApi(auth.client);
      onGenerated(await api.generatePatientSummary(memberId, newIdempotencyKey()));
    } catch (cause) {
      setError(hospitalErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="consult-card" aria-label="AI 辅助摘要">
      <header className="consult-card__head">
        <h3>AI 辅助摘要（医生参考）</h3>
        <button type="button" className="doctor-button doctor-button--ghost patient-button-inline" disabled={busy} onClick={() => void generate()}>
          {busy ? "生成中…" : summary ? "重新生成" : "生成摘要"}
        </button>
      </header>
      {error ? <p className="patient-module__error" role="alert">{error}</p> : null}
      {summary ? (
        <p className="consult-card__text">{summary.sections.current_issues || summary.sections.conversation_highlights || "暂无内容"}</p>
      ) : (
        <p className="patient-module__hint">基于本次问诊内容生成摘要，供医生参考。</p>
      )}
    </section>
  );
}

/** DOCTOR-WORKSPACE-000004 独立线上问诊页右侧问诊详情（按参考图实现）：
 *  状态与结束操作 / 患者基础资料 / 病历与附件 / 消息与回复 / 风险与关注 / AI 摘要。 */
export function ConsultDetailPanel() {
  const auth = useOptionalAuth();
  const conversations = useOptionalDoctorConversations();
  const detail = conversations?.detail ?? null;
  const memberId = detail?.member_id ?? null;
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const follow = useDoctorMessageFollow(scrollRef, conversations?.messages ?? [], conversations?.selectedThreadId ?? null);

  const [profile, setProfile] = useState<PatientWorkspaceDTO | null>(null);
  const [attachments, setAttachments] = useState<ConversationAttachmentItemDTO[] | null>(null);
  const [summary, setSummary] = useState<PatientSummaryDTO | null>(null);

  const threadId = detail?.thread_id ?? null;
  useEffect(() => {
    setProfile(null);
    setAttachments(null);
    setSummary(null);
    if (!auth || !threadId) return;
    const api = new SparkHospitalApi(auth.client);
    let cancelled = false;
    void api.getConversationAttachments(threadId).then((data) => { if (!cancelled) setAttachments(data.items); }).catch(() => undefined);
    if (memberId !== null) {
      void api.getPatientWorkspace(memberId).then((data) => { if (!cancelled) setProfile(data); }).catch(() => undefined);
      void api.getPatientSummary(memberId).then((data) => { if (!cancelled) setSummary(data); }).catch(() => undefined);
    }
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth, threadId, memberId, detail?.attachment_count]);

  if (!conversations || !detail) return null;
  const status = detail.service_status;

  return (
    <aside className="patient-aside patient-aside--drawer consult-detail" aria-label="问诊详情">
      <header className="patient-drawer__head consult-detail__head">
        <div>
          <h2>问诊详情</h2>
          <p>
            {detail.patient_display_name || "患者"}
            {detail.consult_no ? ` · 问诊编号：${detail.consult_no}` : ` · ${detail.title || detail.agent.name}`}
          </p>
        </div>
        <span className={`doctor-tag doctor-tag--status-${status}`}>{SERVICE_STATUS_LABEL[status]}</span>
        {detail.doctor_attention_level === "priority" && (
          <span className="patient-tag-priority"><Star size={11} strokeWidth={2.4} />重点患者</span>
        )}
        <EndConversationSection />
      </header>

      <div className="consult-detail__scroll">
        <div className="consult-detail__top">
          <PatientProfileCard profile={profile} />
          <AttachmentsCard items={attachments} />
        </div>
        <TakeoverBar />
        <div className="doctor-scroll-frame patient-drawer__scroll consult-detail__messages">
          <div className="chat-scroll" data-chat-scroll-root ref={scrollRef}>
            <section className="message-column patient-drawer__messages">
              <DoctorMessages variant="consult" />
            </section>
          </div>
          {follow.showNewMessages && (
            <button type="button" className="doctor-new-messages" onClick={follow.jumpToLatest}>
              <ArrowDown size={13} strokeWidth={2.2} />
              有 {follow.unseenCount} 条新消息
            </button>
          )}
        </div>
        <AttentionSection />
      </div>

      <div className="composer-wrap patient-drawer__composer"><DoctorComposer /></div>

      <div className="consult-detail__bottom">
        {memberId !== null ? <SummaryCard memberId={memberId} summary={summary} onGenerated={setSummary} /> : null}
        <ConversationRiskPanel />
      </div>
    </aside>
  );
}
