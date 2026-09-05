"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Search, Star } from "lucide-react";
import { ConsultDetailPanel } from "@/components/doctor/ConsultDetailPanel";
import { useOptionalAuth } from "@/context/AuthContext";
import { useOptionalDoctorConversations } from "@/context/DoctorConversationsContext";
import { SparkHospitalApi } from "@/lib/api/hospital-api";
import { hospitalErrorMessage } from "@/lib/hospital/errors";
import {
  GENDER_LABEL,
  PATIENT_QUEUE_LABEL,
  SERVICE_STATUS_LABEL,
  patientListTime,
} from "@/lib/hospital/labels";
import type {
  ConsultRecordDTO,
  ConversationQueueCounts,
  PatientCardDTO,
  PatientQueue,
  PatientWorkspaceDTO,
} from "@/types/hospital";

/** 参考图筛选：全部 / 待接诊 / 问诊中 / 已结束（重点患者以标记与排序体现）。 */
const QUEUES = ["all", "pending", "active", "ended"] as const satisfies readonly PatientQueue[];

const EMPTY_COUNTS: ConversationQueueCounts = { all: 0, pending: 0, joined: 0, priority: 0, active: 0, ended: 0 };
const PAGE_SIZE = 10;

function consultMemberId(pathname: string | null): number | null {
  const match = (pathname ?? "").match(/\/doctor\/consult\/(\d+)/);
  return match?.[1] ? Number.parseInt(match[1], 10) : null;
}

/** 中间栏患者头部（参考图：头像 / 姓名 / 性别年龄 / 编号 / 状态与重点标记 / 查看患者资料）。 */
function ConsultPatientHeader({ profile, fallback }: { profile: PatientWorkspaceDTO | null; fallback: PatientCardDTO | null }) {
  if (!profile && !fallback) return null;
  const patient = profile?.patient;
  return (
    <section className="patient-identity consult-patient-head" aria-label="当前患者">
      <span className="patient-identity__avatar" aria-hidden="true">
        {patient?.avatar_url
          // eslint-disable-next-line @next/next/no-img-element
          ? <img src={patient.avatar_url} alt="" />
          : (patient?.display_name || fallback?.display_name || "患").slice(0, 1)}
      </span>
      <div className="patient-identity__main">
        <h1>
          {patient?.display_name || fallback?.display_name || "未命名患者"}
          <span className="patient-identity__sub">
            {patient ? (GENDER_LABEL[patient.gender] ?? "未填写") : ""}
            {patient?.age !== null && patient ? ` · ${patient.age}岁` : ""}
          </span>
          {patient?.priority_patient || fallback?.priority_patient ? (
            <span className="patient-tag-priority"><Star size={11} strokeWidth={2.4} />重点患者</span>
          ) : null}
        </h1>
        <p>
          患者编号：{patient?.patient_number || "未生成"}
          {patient?.service_status
            ? <span className={`doctor-tag doctor-tag--status-${patient.service_status}`}>{SERVICE_STATUS_LABEL[patient.service_status]}</span>
            : null}
        </p>
      </div>
      {profile?.patient.member_id ? (
        <Link className="doctor-button doctor-button--ghost patient-button-inline consult-patient-head__profile" href={`/doctor/patients/${profile.patient.member_id}` as never}>
          查看患者资料
        </Link>
      ) : null}
    </section>
  );
}

/** 中间栏问诊记录卡片（参考图：时间 / 独立问诊 / 状态 / 患者首句 / 附件数 / 医生已回复）。 */
function ConsultRecordRow({ card, open, fresh, onOpen }: { card: ConsultRecordDTO; open: boolean; fresh: boolean; onOpen: () => void }) {
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

/** DOCTOR-WORKSPACE-000004：独立“线上问诊”页（按参考图实现）。
 *
 * 左侧已发起问诊的患者聚合列表；中间当前患者与其独立问诊记录（分页）；
 * 右侧当前选中问诊的详情、资料、附件、消息与回复区。
 */
export function ConsultWorkspacePage() {
  const auth = useOptionalAuth();
  const router = useRouter();
  const pathname = usePathname();
  const conversationsCtx = useOptionalDoctorConversations();
  const api = useMemo(() => (auth ? new SparkHospitalApi(auth.client) : null), [auth]);

  const memberId = consultMemberId(pathname ?? null);

  // ---------- 左侧患者列表 ----------
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

  // 实时事件驱动的会话计数变化时，合并刷新患者列表与问诊记录（防抖 400ms）。
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

  // ---------- 中间问诊记录 ----------
  const [records, setRecords] = useState<ConsultRecordDTO[]>([]);
  const [recordsStatus, setRecordsStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [recordsError, setRecordsError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [profile, setProfile] = useState<PatientWorkspaceDTO | null>(null);

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
  const loadRecordsRef = useRef(loadRecords);
  loadRecordsRef.current = loadRecords;

  useEffect(() => {
    setPage(1);
    void loadRecords();
  }, [loadRecords]);

  const selectedPatient = patients.find((patient) => patient.member_id === memberId) ?? null;
  const totalPages = Math.max(1, Math.ceil(records.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageRecords = records.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

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

      <main className="patient-main" aria-label="线上问诊记录">
        {memberId === null ? (
          <div className="empty-state">
            <div>
              <p className="empty-state__eyebrow">线上问诊</p>
              <h1>选择一位患者</h1>
              <p>从左侧列表选择患者后，查看该患者的全部线上问诊记录；问诊由患者客户端发起。</p>
            </div>
          </div>
        ) : (
          <>
            <ConsultPatientHeader profile={profile} fallback={selectedPatient} />
            <section className="patient-section" aria-label="线上问诊记录">
              <header className="patient-section__head">
                <h2>线上问诊记录</h2>
                <span className="consult-record__note">每次问诊为独立对话</span>
              </header>
              {recordsError && (
                <p className="patient-module__error" role="alert">
                  {recordsError}
                  <button type="button" className="doctor-inline-retry" onClick={() => void loadRecords()}>重试</button>
                </p>
              )}
              {recordsStatus === "loading" && !records.length && <p className="patient-module__hint">正在加载问诊记录…</p>}
              {recordsStatus === "ready" && !records.length && !recordsError && (
                <p className="patient-module__hint">该患者还没有由客户端发起的线上问诊。</p>
              )}
              {pageRecords.length > 0 && (
                <ul className="patient-conversation-list">
                  {pageRecords.map((card) => (
                    <ConsultRecordRow
                      key={card.thread_id}
                      card={card}
                      open={conversationsCtx?.selectedThreadId === card.thread_id}
                      fresh={conversationsCtx?.selectedThreadId !== card.thread_id && (conversationsCtx?.newMessageThreadIds.includes(card.thread_id) ?? false)}
                      onOpen={() => conversationsCtx?.selectConversation(card.thread_id)}
                    />
                  ))}
                </ul>
              )}
              {records.length > 0 && (
                <footer className="consult-pagination">
                  <span>共 {records.length} 条</span>
                  <span className="consult-pagination__pages">
                    <button type="button" aria-label="上一页" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={14} /></button>
                    {Array.from({ length: totalPages }, (_, index) => index + 1).map((number) => (
                      <button
                        key={number}
                        type="button"
                        aria-current={number === currentPage ? "page" : undefined}
                        className={number === currentPage ? "is-active" : ""}
                        onClick={() => setPage(number)}
                      >
                        {number}
                      </button>
                    ))}
                    <button type="button" aria-label="下一页" disabled={currentPage >= totalPages} onClick={() => setPage(currentPage + 1)}><ChevronRight size={14} /></button>
                  </span>
                  <span>{PAGE_SIZE} 条/页</span>
                </footer>
              )}
            </section>
          </>
        )}
      </main>

      {conversationsCtx?.selectedThreadId ? (
        <ConsultDetailPanel />
      ) : (
        <aside className="patient-aside patient-aside--aux" aria-label="问诊详情">
          <header className="patient-aside__head">
            <h2>问诊详情</h2>
            <span>未选择问诊</span>
          </header>
          <div className="patient-aside__scroll">
            <p className="patient-aux-card__meta">从中间问诊记录中选择一条问诊，查看患者基础资料、病历与附件、问诊消息，并进行接管、回复、风险调整或结束问诊。</p>
          </div>
        </aside>
      )}
    </div>
  );
}
