"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Search, Star } from "lucide-react";
import { ConsultMainColumn } from "@/components/doctor/ConsultMainColumn";
import { useOptionalAuth } from "@/context/AuthContext";
import { useOptionalDoctorConversations } from "@/context/DoctorConversationsContext";
import { SparkHospitalApi } from "@/lib/api/hospital-api";
import { hospitalErrorMessage } from "@/lib/hospital/errors";
import { PATIENT_QUEUE_LABEL, SERVICE_STATUS_LABEL, patientListTime } from "@/lib/hospital/labels";
import type { ConversationQueueCounts, PatientCardDTO, PatientQueue } from "@/types/hospital";

/** 参考图筛选：全部 / 待接诊 / 问诊中 / 已结束（重点患者以标记与排序体现）。 */
const QUEUES = ["all", "pending", "active", "ended"] as const satisfies readonly PatientQueue[];

const EMPTY_COUNTS: ConversationQueueCounts = { all: 0, pending: 0, joined: 0, priority: 0, active: 0, ended: 0 };

function consultMemberId(pathname: string | null): number | null {
  const match = (pathname ?? "").match(/\/doctor\/consult\/(\d+)/);
  return match?.[1] ? Number.parseInt(match[1], 10) : null;
}

/** DOCTOR-WORKSPACE-000004：独立「线上问诊」页——左侧患者列表 + 右侧问诊工作区（历史记录在 activity 侧栏）。 */
export function ConsultWorkspacePage() {
  const auth = useOptionalAuth();
  const router = useRouter();
  const pathname = usePathname();
  const conversationsCtx = useOptionalDoctorConversations();
  const api = useMemo(() => (auth ? new SparkHospitalApi(auth.client) : null), [auth]);

  const memberId = consultMemberId(pathname ?? null);

  const [queue, setQueue] = useState<PatientQueue>("all");
  const [keyword, setKeyword] = useState("");
  const [patients, setPatients] = useState<PatientCardDTO[]>([]);
  const [counts, setCounts] = useState<ConversationQueueCounts>(EMPTY_COUNTS);
  const [listStatus, setListStatus] = useState<"loading" | "ready" | "error">("loading");
  const [listError, setListError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => setKeyword(searchInput.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const loadPatients = useCallback(async () => {
    if (!api) return;
    try {
      const data = await api.listConsultPatients({ queue, keyword, page: 1, page_size: 50 });
      setPatients(data.items);
      setCounts(data.counts);
      setListStatus("ready");
      setListError(null);
    } catch (cause) {
      setListStatus("error");
      setListError(hospitalErrorMessage(cause));
    }
  }, [api, queue, keyword]);

  useEffect(() => {
    setListStatus("loading");
    void loadPatients();
  }, [loadPatients]);

  const loadRecordsRef = useRef<(() => Promise<void>) | null>(null);
  const registerRecordsRefresh = useCallback((load: () => Promise<void>) => {
    loadRecordsRef.current = load;
  }, []);

  const refreshTimerRef = useRef<number | null>(null);
  const scheduleRefresh = useCallback(() => {
    if (refreshTimerRef.current !== null) window.clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = window.setTimeout(() => {
      void loadPatients();
      void loadRecordsRef.current?.();
    }, 400);
  }, [loadPatients]);

  const conversationCountsKey = JSON.stringify(conversationsCtx?.counts ?? EMPTY_COUNTS);
  useEffect(() => {
    scheduleRefresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationCountsKey]);

  useEffect(() => () => {
    if (refreshTimerRef.current !== null) window.clearTimeout(refreshTimerRef.current);
  }, []);

  return (
    <div className="patient-workspace consult-workspace">
      <aside className="patient-list-panel" aria-label="问诊患者列表">
        <h2 className="consult-list-title">线上问诊</h2>
        <label className="sidebar-search patient-list-search">
          <Search size={13} />
          <input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="搜索患者姓名或编号…"
            aria-label="搜索患者姓名或编号"
          />
        </label>
        <div className="doctor-queue-tabs patient-queue-tabs" role="tablist" aria-label="患者筛选">
          {QUEUES.map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={queue === item}
              className="doctor-queue-tab"
              onClick={() => setQueue(item)}
            >
              <span>{PATIENT_QUEUE_LABEL[item]}</span>
              <em>{counts[item] ?? 0}</em>
            </button>
          ))}
        </div>
        {listError && (
          <p className="sidebar__notice" role="alert">
            {listError}
            <button type="button" className="doctor-inline-retry" onClick={() => void loadPatients()}>重试</button>
          </p>
        )}
        {listStatus === "loading" && patients.length === 0 && <p className="sidebar__notice">正在加载患者…</p>}
        <ul className="patient-card-list">
          {patients.map((patient) => {
            const selected = memberId === patient.member_id;
            const unread = patient.unread_count ?? 0;
            return (
              <li key={patient.member_id}>
                <button
                  type="button"
                  className="patient-card"
                  aria-current={selected ? "true" : undefined}
                  onClick={() => router.push(`/doctor/consult/${patient.member_id}` as never)}
                >
                  <span className="patient-card__avatar" aria-hidden="true">{(patient.display_name || "患").slice(0, 1)}</span>
                  <span className="patient-card__body">
                    <span className="patient-card__title">
                      <strong>{patient.display_name || "未命名患者"}</strong>
                      {patient.priority_patient && (
                        <em className="patient-card__priority"><Star size={11} strokeWidth={2.4} />重点患者</em>
                      )}
                      {unread > 0 && <b className="doctor-card__unread" aria-label={`${unread} 条未读`}>{unread > 99 ? "99+" : unread}</b>}
                    </span>
                    <span className="patient-card__meta">{patient.masked_patient_identifier}</span>
                  </span>
                  <span className="consult-patient-card__side">
                    {patient.service_status && (
                      <span className={`doctor-tag doctor-tag--status-${patient.service_status}`}>
                        {SERVICE_STATUS_LABEL[patient.service_status]}
                      </span>
                    )}
                    <em>{patientListTime(patient.latest_conversation_at)}</em>
                  </span>
                </button>
              </li>
            );
          })}
          {listStatus === "ready" && patients.length === 0 && (
            <li className="sidebar__notice">未找到已提交线上问诊的患者</li>
          )}
        </ul>
      </aside>

      <ConsultMainColumn memberId={memberId} onRecordsRefresh={registerRecordsRefresh} />
    </div>
  );
}
