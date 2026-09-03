"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { SparkHospitalApi } from "@/lib/api/hospital-api";
import { useOptionalAuth } from "@/context/AuthContext";
import { useOptionalDoctorConversations } from "@/context/DoctorConversationsContext";
import { useDoctorAuth } from "@/context/DoctorAuthGate";
import { hospitalErrorMessage, isHospitalError, newIdempotencyKey } from "@/lib/hospital/errors";
import { CoalescedRefreshScheduler } from "@/lib/hospital/realtime";
import {
  clearAllPatientCache,
  clearPatientCache,
  ensurePatientCacheIdentity,
  readPatientCache,
  writePatientCache,
  type PatientCacheModule,
} from "@/lib/hospital/patient-cache";
import type {
  ConversationCardDTO,
  ConversationQueueCounts,
  HospitalConversationUpdatedEvent,
  PatientCardDTO,
  PatientQueue,
  PatientRiskCardDTO,
  PatientSummaryDTO,
  PatientWorkspaceDTO,
} from "@/types/hospital";

const EMPTY_COUNTS: ConversationQueueCounts = { all: 0, pending: 0, priority: 0, ended: 0 };

type LoadStatus = "idle" | "loading" | "ready" | "error";

/** 模块状态：data 存在时优先展示（含缓存），error 与 data 可并存（局部失败保留旧缓存）。 */
export interface PatientModuleState<T> {
  status: LoadStatus;
  error: string | null;
  data: T | null;
  /** 数据来自缓存时的写入时间；服务端新快照为 null。 */
  cachedAt: string | null;
  /** 缓存已超过模块 TTL（仅作刷新前临时展示）。 */
  stale: boolean;
}

function idleModule<T>(): PatientModuleState<T> {
  return { status: "idle", error: null, data: null, cachedAt: null, stale: false };
}

interface PatientWorkspaceValue {
  active: boolean;
  // 患者列表（D-007~D-010）
  listStatus: LoadStatus;
  listError: string | null;
  queue: PatientQueue;
  keyword: string;
  counts: ConversationQueueCounts;
  patients: PatientCardDTO[];
  setQueue: (queue: PatientQueue) => void;
  setKeyword: (keyword: string) => void;
  reloadList: () => Promise<void>;
  // 患者选择
  selectedMemberId: number | null;
  selectPatient: (memberId: number | null) => void;
  // 工作台模块（D-029：缓存先行 + 并行刷新；AI 总结按需）
  profile: PatientModuleState<PatientWorkspaceDTO>;
  conversations: PatientModuleState<ConversationCardDTO[]>;
  summary: PatientModuleState<PatientSummaryDTO | null>;
  risk: PatientModuleState<PatientRiskCardDTO | null>;
  retryModule: (module: PatientCacheModule) => void;
  refreshRisk: () => Promise<void>;
  // 医生操作
  actionBusy: boolean;
  actionError: string | null;
  createConversation: () => Promise<string | null>;
  generateSummary: () => Promise<boolean>;
  setSummaryAcknowledged: (acknowledged: boolean) => Promise<boolean>;
  // 实时（BACKOFFICE-CONVERSATION-000002 事件 → 患者列表/模块合并刷新）
  handleRealtimeEvent: (event: HospitalConversationUpdatedEvent) => void;
  refreshForRecovery: () => void;
}

const PatientWorkspaceContext = createContext<PatientWorkspaceValue | null>(null);

function pathMemberId(pathname: string | null): number | null {
  const match = (pathname ?? "").match(/\/doctor\/patients\/(\d+)/);
  return match?.[1] ? Number.parseInt(match[1], 10) : null;
}

export function PatientWorkspaceProvider({ children }: { children: React.ReactNode }) {
  const auth = useOptionalAuth();
  const { hospital, doctor } = useDoctorAuth();
  const router = useRouter();
  const pathname = usePathname();
  const conversationsCtx = useOptionalDoctorConversations();
  const api = useMemo(() => (auth ? new SparkHospitalApi(auth.client) : null), [auth]);

  const active = (pathname ?? "").startsWith("/doctor/patients");

  const [listStatus, setListStatus] = useState<LoadStatus>("idle");
  const [listError, setListError] = useState<string | null>(null);
  const [queue, setQueueState] = useState<PatientQueue>("all");
  const [keyword, setKeywordState] = useState("");
  const [counts, setCounts] = useState<ConversationQueueCounts>(EMPTY_COUNTS);
  const [patients, setPatients] = useState<PatientCardDTO[]>([]);
  const [selectedMemberId, setSelectedMemberId] = useState<number | null>(() => pathMemberId(pathname ?? null));

  const [profile, setProfile] = useState<PatientModuleState<PatientWorkspaceDTO>>(idleModule);
  const [patientConversations, setPatientConversations] = useState<PatientModuleState<ConversationCardDTO[]>>(idleModule);
  const [summary, setSummary] = useState<PatientModuleState<PatientSummaryDTO | null>>(idleModule);
  const [risk, setRisk] = useState<PatientModuleState<PatientRiskCardDTO | null>>(idleModule);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const queueRef = useRef(queue);
  const keywordRef = useRef(keyword);
  queueRef.current = queue;
  keywordRef.current = keyword;
  const selectedMemberIdRef = useRef(selectedMemberId);
  selectedMemberIdRef.current = selectedMemberId;
  /** 模块请求世代：切换患者后丢弃旧患者的迟到响应。 */
  const moduleGenerationRef = useRef(0);

  const scopeFor = useCallback((memberId: number, module: PatientCacheModule) => ({
    hospitalId: hospital.id,
    doctorId: doctor.id,
    memberId,
    module,
  }), [doctor.id, hospital.id]);

  /* ---------- 身份与缓存生命周期（D-030/D-031） ---------- */

  useEffect(() => {
    ensurePatientCacheIdentity(hospital.id, doctor.id);
  }, [doctor.id, hospital.id]);

  useEffect(() => {
    if (auth?.status && auth.status !== "authenticated") clearAllPatientCache();
  }, [auth?.status]);

  /* ---------- 患者列表 ---------- */

  const reloadList = useCallback(async () => {
    if (!api || auth?.status !== "authenticated") return;
    setListStatus("loading");
    setListError(null);
    try {
      const data = await api.listPatients({ queue: queueRef.current, keyword: keywordRef.current, page: 1, page_size: 50 });
      setPatients(data.items);
      setCounts(data.counts);
      setListStatus("ready");
    } catch (cause) {
      setListStatus("error");
      setListError(hospitalErrorMessage(cause));
    }
  }, [api, auth?.status]);

  const reloadListRef = useRef(reloadList);
  reloadListRef.current = reloadList;
  const listRefreshRef = useRef<CoalescedRefreshScheduler | null>(null);
  if (listRefreshRef.current === null) {
    listRefreshRef.current = new CoalescedRefreshScheduler(() => reloadListRef.current(), 250);
  }
  const scheduleListRefresh = useCallback(() => { listRefreshRef.current?.request(); }, []);

  useEffect(() => () => { listRefreshRef.current?.dispose(); }, []);

  useEffect(() => {
    if (!active) return;
    void reloadList();
  }, [active, reloadList, queue, keyword]);

  useEffect(() => {
    setSelectedMemberId(pathMemberId(pathname ?? null));
  }, [pathname]);

  const selectPatient = useCallback((memberId: number | null) => {
    setActionError(null);
    router.push((memberId !== null ? `/doctor/patients/${memberId}` : "/doctor/patients") as never);
  }, [router]);

  // 进入患者页且未选择患者时默认选中第一位（D-011：只约束不自动打开会话）。
  useEffect(() => {
    if (!active || pathMemberId(pathname ?? null) !== null) return;
    if (listStatus !== "ready" || patients.length === 0) return;
    router.replace((`/doctor/patients/${patients[0].member_id}`) as never);
  }, [active, listStatus, patients, pathname, router]);

  /* ---------- 无权限患者处理（D-007/Q-004：立即移除并退回列表） ---------- */

  const dropPatient = useCallback((memberId: number) => {
    clearPatientCache({ hospitalId: hospital.id, doctorId: doctor.id, memberId });
    setPatients((current) => current.filter((item) => item.member_id !== memberId));
    if (selectedMemberIdRef.current === memberId) {
      setListError("已无该患者访问权限，已从列表移除。");
      router.push("/doctor/patients" as never);
    }
  }, [doctor.id, hospital.id, router]);

  const guardPatientError = useCallback((cause: unknown, memberId: number): boolean => {
    if (isHospitalError(cause, "PATIENT_NOT_ASSIGNED") || isHospitalError(cause, "PATIENT_CONSENT_REQUIRED")) {
      dropPatient(memberId);
      return true;
    }
    return false;
  }, [dropPatient]);

  /* ---------- 模块加载：缓存先行 + 后台并行刷新（D-029） ---------- */

  const loadProfile = useCallback(async (memberId: number, generation: number) => {
    if (!api) return;
    const cached = readPatientCache<PatientWorkspaceDTO>(scopeFor(memberId, "profile"));
    setProfile(cached
      ? { status: "ready", error: null, data: cached.data, cachedAt: cached.savedAt, stale: cached.stale }
      : { status: "loading", error: null, data: null, cachedAt: null, stale: false });
    try {
      const data = await api.getPatientWorkspace(memberId);
      if (moduleGenerationRef.current !== generation) return;
      writePatientCache(scopeFor(memberId, "profile"), data);
      setProfile({ status: "ready", error: null, data, cachedAt: null, stale: false });
    } catch (cause) {
      if (moduleGenerationRef.current !== generation) return;
      if (guardPatientError(cause, memberId)) return;
      setProfile((current) => ({ ...current, status: "error", error: hospitalErrorMessage(cause) }));
    }
  }, [api, guardPatientError, scopeFor]);

  const loadConversations = useCallback(async (memberId: number, generation: number) => {
    if (!api) return;
    const cached = readPatientCache<ConversationCardDTO[]>(scopeFor(memberId, "conversations"));
    setPatientConversations(cached
      ? { status: "ready", error: null, data: cached.data, cachedAt: cached.savedAt, stale: cached.stale }
      : { status: "loading", error: null, data: null, cachedAt: null, stale: false });
    try {
      const data = await api.getPatientConversations(memberId);
      if (moduleGenerationRef.current !== generation) return;
      writePatientCache(scopeFor(memberId, "conversations"), data.items);
      setPatientConversations({ status: "ready", error: null, data: data.items, cachedAt: null, stale: false });
    } catch (cause) {
      if (moduleGenerationRef.current !== generation) return;
      if (guardPatientError(cause, memberId)) return;
      setPatientConversations((current) => ({ ...current, status: "error", error: hospitalErrorMessage(cause) }));
    }
  }, [api, guardPatientError, scopeFor]);

  const loadRisk = useCallback(async (memberId: number, generation: number) => {
    if (!api) return;
    const cached = readPatientCache<PatientRiskCardDTO | null>(scopeFor(memberId, "risk"));
    setRisk(cached
      ? { status: "ready", error: null, data: cached.data, cachedAt: cached.savedAt, stale: cached.stale }
      : { status: "loading", error: null, data: null, cachedAt: null, stale: false });
    try {
      const data = await api.getPatientRisk(memberId);
      if (moduleGenerationRef.current !== generation) return;
      writePatientCache(scopeFor(memberId, "risk"), data);
      setRisk({ status: "ready", error: null, data, cachedAt: null, stale: false });
    } catch (cause) {
      if (moduleGenerationRef.current !== generation) return;
      if (guardPatientError(cause, memberId)) return;
      setRisk((current) => ({ ...current, status: "error", error: hospitalErrorMessage(cause) }));
    }
  }, [api, guardPatientError, scopeFor]);

  // D-029：AI 总结不随页面进入自动请求，只展示已有缓存结果或“生成总结”入口。
  const loadSummaryFromCache = useCallback((memberId: number) => {
    const cached = readPatientCache<PatientSummaryDTO | null>(scopeFor(memberId, "summary"));
    setSummary(cached
      ? { status: "ready", error: null, data: cached.data, cachedAt: cached.savedAt, stale: cached.stale }
      : { status: "ready", error: null, data: null, cachedAt: null, stale: false });
  }, [scopeFor]);

  useEffect(() => {
    if (!active || auth?.status !== "authenticated" || selectedMemberId === null) {
      moduleGenerationRef.current += 1;
      setProfile(idleModule());
      setPatientConversations(idleModule());
      setSummary(idleModule());
      setRisk(idleModule());
      return;
    }
    const memberId = selectedMemberId;
    moduleGenerationRef.current += 1;
    const generation = moduleGenerationRef.current;
    loadSummaryFromCache(memberId);
    // 后台并行刷新：患者资料、患者会话列表、风险结果互不阻塞（D-029 第 3 步）。
    void loadProfile(memberId, generation);
    void loadConversations(memberId, generation);
    void loadRisk(memberId, generation);
  }, [active, auth?.status, selectedMemberId, loadProfile, loadConversations, loadRisk, loadSummaryFromCache]);

  const retryModule = useCallback((module: PatientCacheModule) => {
    const memberId = selectedMemberIdRef.current;
    if (memberId === null) return;
    moduleGenerationRef.current += 1;
    const generation = moduleGenerationRef.current;
    if (module === "profile") void loadProfile(memberId, generation);
    else if (module === "conversations") void loadConversations(memberId, generation);
    else if (module === "risk") void loadRisk(memberId, generation);
    else loadSummaryFromCache(memberId);
  }, [loadConversations, loadProfile, loadRisk, loadSummaryFromCache]);

  const refreshRisk = useCallback(async () => {
    const memberId = selectedMemberIdRef.current;
    if (memberId === null) return;
    moduleGenerationRef.current += 1;
    await loadRisk(memberId, moduleGenerationRef.current);
  }, [loadRisk]);

  /* ---------- 抽屉内会话写操作 → 患者模块合并刷新 ---------- */

  // 调度器闭包在首次渲染即创建（彼时 api 可能尚未就绪），必须通过 ref 调用最新加载器。
  const loadProfileRef = useRef(loadProfile);
  loadProfileRef.current = loadProfile;
  const loadConversationsRef = useRef(loadConversations);
  loadConversationsRef.current = loadConversations;
  const loadRiskRef = useRef(loadRisk);
  loadRiskRef.current = loadRisk;

  const modulesRefreshRef = useRef<CoalescedRefreshScheduler | null>(null);
  if (modulesRefreshRef.current === null) {
    modulesRefreshRef.current = new CoalescedRefreshScheduler(async () => {
      const memberId = selectedMemberIdRef.current;
      if (memberId === null) return;
      moduleGenerationRef.current += 1;
      const generation = moduleGenerationRef.current;
      void loadProfileRef.current(memberId, generation);
      void loadConversationsRef.current(memberId, generation);
      void loadRiskRef.current(memberId, generation);
      await reloadListRef.current();
    }, 250);
  }
  const scheduleModulesRefresh = useCallback(() => { modulesRefreshRef.current?.request(); }, []);
  useEffect(() => () => { modulesRefreshRef.current?.dispose(); }, []);

  const drawerDetail = conversationsCtx?.detail ?? null;
  const drawerStamp = drawerDetail ? `${drawerDetail.thread_id}:${drawerDetail.version}:${drawerDetail.updated_at}` : null;
  const prevDrawerStampRef = useRef<string | null>(null);
  useEffect(() => {
    if (prevDrawerStampRef.current === drawerStamp) return;
    prevDrawerStampRef.current = drawerStamp;
    if (!drawerStamp) return;
    scheduleModulesRefresh();
  }, [drawerStamp, scheduleModulesRefresh]);

  /* ---------- 实时事件（BACKOFFICE-CONVERSATION-000002） ---------- */

  const handleRealtimeEvent = useCallback((event: HospitalConversationUpdatedEvent) => {
    if (!event || event.type !== "hospital.conversation.updated") return;
    if (!active) return;
    // 患者列表（最近会话时间/服务状态/计数）与当前患者模块合并刷新。
    scheduleListRefresh();
    if (selectedMemberIdRef.current !== null) scheduleModulesRefresh();
  }, [active, scheduleListRefresh, scheduleModulesRefresh]);

  const refreshForRecovery = useCallback(() => {
    if (!active) return;
    scheduleListRefresh();
    if (selectedMemberIdRef.current !== null) scheduleModulesRefresh();
  }, [active, scheduleListRefresh, scheduleModulesRefresh]);

  /* ---------- 医生操作 ---------- */

  const setQueue = useCallback((next: PatientQueue) => { setQueueState(next); }, []);
  const setKeyword = useCallback((next: string) => { setKeywordState(next); }, []);

  /** D-019：新建咨询，服务端重新校验并创建新 Thread；成功后刷新列表并打开抽屉。 */
  const createConversation = useCallback(async (): Promise<string | null> => {
    const memberId = selectedMemberIdRef.current;
    if (!api || memberId === null || actionBusy) return null;
    setActionBusy(true);
    setActionError(null);
    try {
      const detail = await api.createPatientConversation(memberId, newIdempotencyKey());
      scheduleModulesRefresh();
      conversationsCtx?.selectConversation(detail.thread_id);
      return detail.thread_id;
    } catch (cause) {
      if (!guardPatientError(cause, memberId)) setActionError(hospitalErrorMessage(cause));
      return null;
    } finally {
      setActionBusy(false);
    }
  }, [actionBusy, api, conversationsCtx, guardPatientError, scheduleModulesRefresh]);

  /** D-020：医生主动生成/刷新 AI 总结；成功后才更新模块与缓存。 */
  const generateSummary = useCallback(async (): Promise<boolean> => {
    const memberId = selectedMemberIdRef.current;
    if (!api || memberId === null || actionBusy) return false;
    setActionBusy(true);
    setActionError(null);
    setSummary((current) => ({ ...current, status: current.data ? current.status : "loading", error: null }));
    try {
      const data = await api.generatePatientSummary(memberId, newIdempotencyKey());
      if (selectedMemberIdRef.current !== memberId) return false;
      writePatientCache(scopeFor(memberId, "summary"), data);
      setSummary({ status: "ready", error: null, data, cachedAt: null, stale: false });
      return true;
    } catch (cause) {
      if (selectedMemberIdRef.current !== memberId) return false;
      if (!guardPatientError(cause, memberId)) {
        setSummary((current) => ({ ...current, status: "error", error: hospitalErrorMessage(cause) }));
      }
      return false;
    } finally {
      setActionBusy(false);
    }
  }, [actionBusy, api, guardPatientError, scopeFor]);

  /** D-023：标记/取消“已了解”；不改变总结正文。 */
  const setSummaryAcknowledged = useCallback(async (acknowledged: boolean): Promise<boolean> => {
    const memberId = selectedMemberIdRef.current;
    if (!api || memberId === null || actionBusy) return false;
    setActionBusy(true);
    setActionError(null);
    try {
      const data = await api.ackPatientSummary(memberId, acknowledged);
      if (selectedMemberIdRef.current !== memberId) return false;
      writePatientCache(scopeFor(memberId, "summary"), data);
      setSummary({ status: "ready", error: null, data, cachedAt: null, stale: false });
      return true;
    } catch (cause) {
      if (selectedMemberIdRef.current !== memberId) return false;
      if (!guardPatientError(cause, memberId)) setActionError(hospitalErrorMessage(cause));
      return false;
    } finally {
      setActionBusy(false);
    }
  }, [actionBusy, api, guardPatientError, scopeFor]);

  const value = useMemo<PatientWorkspaceValue>(() => ({
    active,
    listStatus,
    listError,
    queue,
    keyword,
    counts,
    patients,
    setQueue,
    setKeyword,
    reloadList,
    selectedMemberId,
    selectPatient,
    profile,
    conversations: patientConversations,
    summary,
    risk,
    retryModule,
    refreshRisk,
    actionBusy,
    actionError,
    createConversation,
    generateSummary,
    setSummaryAcknowledged,
    handleRealtimeEvent,
    refreshForRecovery,
  }), [
    actionBusy, actionError, active, counts, createConversation, generateSummary, handleRealtimeEvent, keyword,
    listError, listStatus, patientConversations, patients, profile, queue, refreshForRecovery, refreshRisk,
    reloadList, retryModule, risk, selectPatient, selectedMemberId, setKeyword, setQueue, setSummaryAcknowledged,
    summary,
  ]);

  return <PatientWorkspaceContext.Provider value={value}>{children}</PatientWorkspaceContext.Provider>;
}

export function usePatientWorkspace() {
  const value = useContext(PatientWorkspaceContext);
  if (!value) throw new Error("usePatientWorkspace must be used inside PatientWorkspaceProvider");
  return value;
}

export function useOptionalPatientWorkspace() {
  return useContext(PatientWorkspaceContext);
}
