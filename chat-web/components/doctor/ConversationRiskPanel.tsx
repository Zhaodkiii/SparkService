"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useEffect, useState } from "react";
import { useOptionalAuth } from "@/context/AuthContext";
import { useOptionalDoctorConversations } from "@/context/DoctorConversationsContext";
import { SparkHospitalApi } from "@/lib/api/hospital-api";
import { RISK_LABEL, formatClock, relativeTime } from "@/lib/hospital/labels";
import type { RiskRevisionDTO, RiskSignalLevel } from "@/types/hospital";

const RISK_OPTIONS: RiskSignalLevel[] = ["none", "low", "medium", "high"];

/** DOCTOR-WORKSPACE-000004 第 24/25/26 问：风险当前值 + 人工调整 + 本问诊调整历史。
 *
 * - 四级可调（含降为无风险），理由可选；
 * - 人工调整不改变问诊服务状态；AI/工具原始结果不被覆盖；
 * - 历史只读，仅当前归属医生可见。
 */
export function ConversationRiskPanel() {
  const auth = useOptionalAuth();
  const conversations = useOptionalDoctorConversations();
  const detail = conversations?.detail ?? null;
  const [level, setLevel] = useState<RiskSignalLevel>("none");
  const [reason, setReason] = useState("");
  const [editing, setEditing] = useState(false);
  const [history, setHistory] = useState<RiskRevisionDTO[] | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  useEffect(() => {
    setLevel(detail?.risk_signal_level ?? "none");
    setReason("");
    setEditing(false);
    setHistory(null);
    setHistoryOpen(false);
    setHistoryError(null);
  }, [detail?.thread_id, detail?.risk_signal_level]);

  if (!conversations || !detail) return null;
  const ended = detail.service_status === "ended";
  const busy = conversations.writeBusy;

  const loadHistory = async () => {
    if (!auth) return;
    if (history !== null) {
      setHistoryOpen((current) => !current);
      return;
    }
    setHistoryError(null);
    try {
      const api = new SparkHospitalApi(auth.client);
      const data = await api.getRiskHistory(detail.thread_id);
      setHistory(data.items);
      setHistoryOpen(true);
    } catch {
      setHistoryError("风险历史加载失败，请稍后重试。");
    }
  };

  const submit = async () => {
    const ok = await conversations.updateRisk(level, reason.trim() || undefined);
    if (ok) {
      setEditing(false);
      setReason("");
      setHistory(null);
      setHistoryOpen(false);
    }
  };

  return (
    <section className="patient-drawer__risk" aria-label="风险等级">
      <header className="patient-drawer__risk-head">
        <span className={`doctor-tag doctor-tag--risk-${detail.risk_signal_level}`}>{RISK_LABEL[detail.risk_signal_level]}</span>
        <span className="patient-drawer__risk-source">当前有效风险{detail.risk_signal_level === "none" ? "（无信号）" : "（含人工调整）"}</span>
        <span className="patient-drawer__takeover-spacer" />
        <button type="button" className="doctor-button doctor-button--ghost patient-button-inline" onClick={() => void loadHistory()}>
          {historyOpen ? "收起历史" : "调整历史"}
        </button>
        {!ended && !editing && (
          <button type="button" className="doctor-button doctor-button--ghost patient-button-inline" disabled={busy} onClick={() => setEditing(true)}>
            调整风险
          </button>
        )}
      </header>
      {historyError ? <p className="patient-module__error" role="alert">{historyError}</p> : null}
      {historyOpen && history !== null ? (
        history.length ? (
          <ul className="doctor-risk-history" aria-label="风险调整历史">
            {history.map((item) => (
              <li key={item.id}>
                <span>
                  {RISK_LABEL[item.previous_level]} → {RISK_LABEL[item.next_level]}
                </span>
                <em>
                  {item.doctor.display_name} · {formatClock(item.created_at) || relativeTime(item.created_at)}
                  {item.source === "doctor_manual" ? " · 医生人工" : ""}
                </em>
                {item.reason ? <p>{item.reason}</p> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="patient-module__hint">本问诊暂无人工调整记录。</p>
        )
      ) : null}
      {editing && !ended ? (
        <form
          className="doctor-end-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <fieldset>
            <legend>调整风险等级（不改变问诊状态）</legend>
            {RISK_OPTIONS.map((option) => (
              <label key={option}>
                <input type="radio" name="drawer-risk-level" checked={level === option} disabled={busy} onChange={() => setLevel(option)} />
                {RISK_LABEL[option]}
              </label>
            ))}
          </fieldset>
          <textarea value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)} placeholder="调整理由（可选）" aria-label="风险调整理由" />
          <div className="doctor-end-form__footer">
            <button type="button" className="doctor-button doctor-button--ghost patient-button-inline" disabled={busy} onClick={() => setEditing(false)}>取消</button>
            <button type="submit" className="doctor-button patient-button-inline" disabled={busy}>确认调整</button>
          </div>
        </form>
      ) : null}
      <p className="patient-drawer__risk-note">风险提示来自现有风险工具与医生人工调整，不构成诊断或处方结论。</p>
    </section>
  );
}
