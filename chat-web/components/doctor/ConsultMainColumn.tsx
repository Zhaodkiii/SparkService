"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { History, UserRound } from "lucide-react";
import { ConsultDetailPanel } from "@/components/doctor/ConsultDetailPanel";
import { ConsultHistoryPanel } from "@/components/doctor/ConsultHistoryPanel";
import { ConsultPatientProfilePanel } from "@/components/doctor/ConsultPatientProfilePanel";
import { useOptionalAuth } from "@/context/AuthContext";
import { useOptionalDoctorConversations } from "@/context/DoctorConversationsContext";
import { SparkHospitalApi } from "@/lib/api/hospital-api";
import { hospitalErrorMessage } from "@/lib/hospital/errors";
import type { ConsultRecordDTO, ConversationAttachmentItemDTO, PatientCardDTO, PatientWorkspaceDTO } from "@/types/hospital";

/** 右侧主工作区：问诊对话 + 可收起的资料/历史侧栏（activity-panel）。 */
export function ConsultMainColumn({
  memberId,
  onRecordsRefresh,
}: {
  memberId: number | null;
  onRecordsRefresh: (load: () => Promise<void>) => void;
}) {
  const auth = useOptionalAuth();
  const conversations = useOptionalDoctorConversations();
  const api = useMemo(() => (auth ? new SparkHospitalApi(auth.client) : null), [auth]);

  const [records, setRecords] = useState<ConsultRecordDTO[]>([]);
  const [recordsStatus, setRecordsStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [recordsError, setRecordsError] = useState<string | null>(null);
  const [profile, setProfile] = useState<PatientWorkspaceDTO | null>(null);
  const [attachments, setAttachments] = useState<ConversationAttachmentItemDTO[] | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const loadRecords = useCallback(async () => {
    if (!api || memberId === null) {
      setRecords([]);
      setProfile(null);
      setRecordsStatus("idle");
      return;
    }
    setRecordsStatus("loading");
    try {
      const [conversationData, profileData] = await Promise.all([
        api.getConsultRecords(memberId),
        api.getPatientWorkspace(memberId).catch(() => null),
      ]);
      setRecords(conversationData.items);
      setProfile(profileData);
      setRecordsStatus("ready");
      setRecordsError(null);
    } catch (cause) {
      setRecordsStatus("error");
      setRecordsError(hospitalErrorMessage(cause));
    }
  }, [api, memberId]);

  useEffect(() => {
    onRecordsRefresh(loadRecords);
  }, [loadRecords, onRecordsRefresh]);

  useEffect(() => {
    setHistoryOpen(false);
    setProfileOpen(false);
    void loadRecords();
  }, [loadRecords, memberId]);

  const detail = conversations?.detail ?? null;
  const selectedThreadId = conversations?.selectedThreadId ?? null;

  useEffect(() => {
    if (memberId === null || recordsStatus !== "ready" || records.length === 0 || !conversations) return;
    const inList = selectedThreadId !== null && records.some((item) => item.thread_id === selectedThreadId);
    if (!inList) conversations.selectConversation(records[0].thread_id);
  }, [conversations, memberId, records, recordsStatus, selectedThreadId]);

  useEffect(() => {
    if (!api || !detail?.thread_id) {
      setAttachments(null);
      return;
    }
    let cancelled = false;
    setAttachments(null);
    void api.getConversationAttachments(detail.thread_id).then((data) => {
      if (!cancelled) setAttachments(data.items);
    }).catch(() => {
      if (!cancelled) setAttachments([]);
    });
    return () => { cancelled = true; };
  }, [api, detail?.thread_id, detail?.attachment_count]);

  if (memberId === null) {
    return (
      <main className="consult-main-column" aria-label="线上问诊工作区">
        <div className="empty-state">
          <div>
            <p className="empty-state__eyebrow">线上问诊</p>
            <h1>选择一位患者</h1>
            <p>从左侧列表选择患者后，在此查看与回复问诊；资料与历史记录在右侧边栏打开。</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="consult-main-column" aria-label="线上问诊工作区">
      <div className="consult-main-column__toolbar">
        <div className="consult-main-column__toolbar-actions">
          <button
            type="button"
            className="doctor-button doctor-button--ghost patient-button-inline consult-main-column__side-btn"
            aria-expanded={profileOpen}
            onClick={() => {
              setHistoryOpen(false);
              setProfileOpen(true);
            }}
          >
            <UserRound size={14} strokeWidth={2.2} />
            患者资料
          </button>
          <button
            type="button"
            className="doctor-button doctor-button--ghost patient-button-inline consult-main-column__side-btn"
            aria-expanded={historyOpen}
            onClick={() => {
              setProfileOpen(false);
              setHistoryOpen(true);
            }}
          >
            <History size={14} strokeWidth={2.2} />
            问诊记录{records.length > 0 ? `（${records.length}）` : ""}
          </button>
        </div>
        {detail?.consult_no ? (
          <span className="consult-main-column__current">当前问诊：{detail.consult_no}</span>
        ) : (
          <span className="consult-main-column__current consult-main-column__current--muted">请选择一条问诊记录</span>
        )}
      </div>

      {detail ? (
        <ConsultDetailPanel />
      ) : (
        <div className="consult-main-column__placeholder">
          <p className="patient-module__hint">正在打开问诊…若长时间无内容，请点击「问诊记录」选择一条历史问诊。</p>
          <button type="button" className="doctor-button patient-button-inline" onClick={() => setHistoryOpen(true)}>
            查看问诊记录
          </button>
        </div>
      )}

      <ConsultPatientProfilePanel
        open={profileOpen}
        onClose={() => setProfileOpen(false)}
        profile={profile}
        attachments={attachments}
        consultNo={detail?.consult_no}
        doctorName={detail?.doctor?.display_name}
      />

      <ConsultHistoryPanel
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        records={records}
        status={recordsStatus}
        error={recordsError}
        onRetry={() => void loadRecords()}
        onSelect={(threadId) => conversations?.selectConversation(threadId)}
      />
    </main>
  );
}
