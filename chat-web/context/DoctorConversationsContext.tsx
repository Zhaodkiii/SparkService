"use client";
/* eslint-disable react-hooks/refs, react-hooks/set-state-in-effect */

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { SparkHospitalApi, toLocalDoctorMessage } from "@/lib/api/hospital-api";
import { useOptionalAuth } from "@/context/AuthContext";
import { hospitalErrorMessage, newIdempotencyKey } from "@/lib/hospital/errors";
import { resolveHospitalWriteError } from "@/lib/hospital/write-result";
import { CoalescedRefreshScheduler, DirtySyncScheduler, mergeAuthoritativeSnapshot } from "@/lib/hospital/realtime";
import type {
  ConversationCardDTO,
  ConversationDetailDTO,
  ConversationQueue,
  ConversationQueueCounts,
  DoctorAttentionLevel,
  DoctorMessageDTO,
  HospitalConversationUpdatedEvent,
} from "@/types/hospital";

const EMPTY_COUNTS: ConversationQueueCounts = { all: 0, pending: 0, priority: 0, ended: 0 };

type LoadStatus = "idle" | "loading" | "ready" | "error";

interface DoctorConversationsValue {
  status: LoadStatus;
  detailStatus: LoadStatus;
  error: string | null;
  detailError: string | null;
  writeError: string | null;
  writeBusy: boolean;
  queue: ConversationQueue;
  keyword: string;
  counts: ConversationQueueCounts;
  cards: ConversationCardDTO[];
  selectedThreadId: string | null;
  detail: ConversationDetailDTO | null;
  messages: DoctorMessageDTO[];
  /** BACKOFFICE-CONVERSATION-000002 Q3：本页面内存中的“新消息”标记（非当前会话）。 */
  newMessageThreadIds: string[];
  setQueue: (queue: ConversationQueue) => void;
  setKeyword: (keyword: string) => void;
  reload: () => Promise<void>;
  selectConversation: (threadId: string | null) => void;
  reloadSelected: () => Promise<void>;
  join: () => Promise<boolean>;
  /** DOCTOR-WORKSPACE-000001 D-015/D-016：取消接管（医生服务中 → AI 服务中）。 */
  leave: () => Promise<boolean>;
  sendMessage: (text: string) => Promise<boolean>;
  updateAttention: (level: DoctorAttentionLevel, note?: string) => Promise<boolean>;
  endConversation: (endReason: string) => Promise<boolean>;
  /** BACKOFFICE-CONVERSATION-000002：实时事件入口（当前会话定向刷新 / 其他会话列表刷新+标记）。 */
  handleRealtimeEvent: (event: HospitalConversationUpdatedEvent) => void;
  /** BACKOFFICE-CONVERSATION-000002 Q5：连接建立/恢复、页面回前台、网络恢复后的合并补偿。 */
  refreshForRecovery: () => void;
}

const DoctorConversationsContext = createContext<DoctorConversationsValue | null>(null);

function pathThreadId(pathname: string | null): string | null {
  const direct = (pathname ?? "").match(/\/doctor\/conversations\/([^/]+)/);
  if (direct?.[1]) return decodeURIComponent(direct[1]);
  // DOCTOR-WORKSPACE-000001：患者工作台右侧会话抽屉路由 /doctor/patients/<memberId>/conversations/<threadId>。
  const drawer = (pathname ?? "").match(/\/doctor\/patients\/\d+\/conversations\/([^/]+)/);
  return drawer?.[1] ? decodeURIComponent(drawer[1]) : null;
}

/** 患者工作台路由中的 memberId（不在患者页时返回 null）。 */
function pathPatientMemberId(pathname: string | null): number | null {
  const match = (pathname ?? "").match(/\/doctor\/patients\/(\d+)/);
  return match?.[1] ? Number.parseInt(match[1], 10) : null;
}

export function DoctorConversationsProvider({ children }: { children: React.ReactNode }) {
  const auth = useOptionalAuth();
  const router = useRouter();
  const pathname = usePathname();
  const api = useMemo(() => (auth ? new SparkHospitalApi(auth.client) : null), [auth]);
  const [status, setStatus] = useState<LoadStatus>("idle");
  const [detailStatus, setDetailStatus] = useState<LoadStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);
  const [writeBusy, setWriteBusy] = useState(false);
  const [queue, setQueueState] = useState<ConversationQueue>("all");
  const [keyword, setKeywordState] = useState("");
  const [counts, setCounts] = useState<ConversationQueueCounts>(EMPTY_COUNTS);
  const [cards, setCards] = useState<ConversationCardDTO[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(() => pathThreadId(pathname ?? null));
  const [detail, setDetail] = useState<ConversationDetailDTO | null>(null);
  const [messages, setMessages] = useState<DoctorMessageDTO[]>([]);
  const [newMessageThreadIds, setNewMessageThreadIds] = useState<string[]>([]);
  const idempotencyRef = useRef<Record<string, string>>({});
  const queueRef = useRef(queue);
  const keywordRef = useRef(keyword);
  queueRef.current = queue;
  keywordRef.current = keyword;
  const selectedThreadIdRef = useRef(selectedThreadId);
  selectedThreadIdRef.current = selectedThreadId;
  const newMessageRef = useRef<Set<string>>(new Set());
  const optimisticRef = useRef<Map<string, { threadId: string; message: DoctorMessageDTO }>>(new Map());

  const markThreadFresh = useCallback((threadId: string) => {
    if (newMessageRef.current.has(threadId)) return;
    newMessageRef.current.add(threadId);
    setNewMessageThreadIds((current) => (current.includes(threadId) ? current : [...current, threadId]));
  }, []);

  const unmarkThreadFresh = useCallback((threadId: string) => {
    if (!newMessageRef.current.delete(threadId)) return;
    setNewMessageThreadIds((current) => current.filter((id) => id !== threadId));
  }, []);

  const idempotencyKey = useCallback((action: string, threadId: string, rotate = false) => {
    const slot = `${action}:${threadId}`;
    if (rotate || !idempotencyRef.current[slot]) idempotencyRef.current[slot] = newIdempotencyKey();
    return idempotencyRef.current[slot];
  }, []);

  const clearIdempotency = useCallback((action: string, threadId: string) => {
    delete idempotencyRef.current[`${action}:${threadId}`];
  }, []);

  const applyBinding = useCallback((binding: ConversationDetailDTO) => {
    setDetail(binding);
    setCards((current) => {
      const next = current.some((card) => card.thread_id === binding.thread_id)
        ? current.map((card) => (card.thread_id === binding.thread_id ? { ...card, ...binding } : card))
        : [binding, ...current];
      return next;
    });
  }, []);

  const dropConversation = useCallback((threadId: string) => {
    setCards((current) => current.filter((card) => card.thread_id !== threadId));
    setDetail((current) => (current?.thread_id === threadId ? null : current));
    setMessages((current) => (selectedThreadId === threadId ? [] : current));
    unmarkThreadFresh(threadId);
    for (const [key, entry] of optimisticRef.current) {
      if (entry.threadId === threadId) optimisticRef.current.delete(key);
    }
    if (selectedThreadId === threadId) {
      setSelectedThreadId(null);
      const memberId = pathPatientMemberId(pathname ?? null);
      router.push((memberId !== null ? `/doctor/patients/${memberId}` : "/doctor/conversations") as never);
    }
  }, [pathname, router, selectedThreadId, unmarkThreadFresh]);

  const reload = useCallback(async () => {
    if (!api || auth?.status !== "authenticated") return;
    setStatus("loading");
    setError(null);
    try {
      const data = await api.listConversations({ queue: queueRef.current, keyword: keywordRef.current, page: 1, page_size: 50 });
      setCards(data.items);
      setCounts(data.counts);
      setStatus("ready");
    } catch (cause) {
      setStatus("error");
      setError(hospitalErrorMessage(cause));
    }
  }, [api, auth?.status]);

  const loadSelected = useCallback(async (threadId: string | null) => {
    if (!api || auth?.status !== "authenticated" || !threadId) {
      setDetail(null);
      setMessages([]);
      setDetailStatus("idle");
      setDetailError(null);
      return;
    }
    setDetailStatus("loading");
    setDetailError(null);
    try {
      const [nextDetail, nextMessages] = await Promise.all([api.getConversation(threadId), api.getMessages(threadId)]);
      // BACKOFFICE-CONVERSATION-000002 S5：旧响应不得覆盖已切换到其他会话的状态。
      if (selectedThreadIdRef.current !== threadId) return;
      // 服务端完整快照为权威；仅保留尚未被快照确认（稳定 ID）的本线程乐观消息。
      let merged = nextMessages.items;
      if (optimisticRef.current.size) {
        const confirmed = new Set<string>();
        for (const item of nextMessages.items) {
          if (item.server_message_id) confirmed.add(`s:${item.server_message_id}`);
          if (item.client_message_id) confirmed.add(`c:${item.client_message_id}`);
        }
        const pending: DoctorMessageDTO[] = [];
        for (const [key, entry] of optimisticRef.current) {
          const optimistic = entry.message;
          const hit =
            (optimistic.server_message_id && confirmed.has(`s:${optimistic.server_message_id}`)) ||
            (optimistic.client_message_id && confirmed.has(`c:${optimistic.client_message_id}`));
          if (hit) {
            optimisticRef.current.delete(key);
          } else if (entry.threadId === threadId) {
            pending.push(optimistic);
          }
        }
        merged = mergeAuthoritativeSnapshot(nextMessages.items, pending);
      }
      setDetail(nextDetail);
      setMessages(merged);
      setCards((current) => current.map((card) => (card.thread_id === nextDetail.thread_id ? { ...card, ...nextDetail } : card)));
      // BACKOFFICE-CONVERSATION-000002 Q3：成功读取该会话后清除页面内新消息标记；读取失败保留。
      unmarkThreadFresh(threadId);
      setDetailStatus("ready");
    } catch (cause) {
      const resolution = resolveHospitalWriteError(cause);
      if (resolution.dropConversation) {
        dropConversation(threadId);
        setWriteError(resolution.message);
        setDetailStatus("idle");
        return;
      }
      if (selectedThreadIdRef.current !== threadId) return;
      setDetailStatus("error");
      setDetailError(hospitalErrorMessage(cause));
    }
  }, [api, auth?.status, dropConversation, unmarkThreadFresh]);

  // BACKOFFICE-CONVERSATION-000002 Q6/§8.3.3：当前会话与列表刷新调度器。
  // 医生发送、实时事件、补偿恢复与切换会话均进入同一 per-thread 队列，
  // 避免并发请求的旧响应覆盖新状态；列表刷新使用独立的短时合并调度。
  const loadSelectedRef = useRef(loadSelected);
  loadSelectedRef.current = loadSelected;
  const reloadRef = useRef(reload);
  reloadRef.current = reload;
  const threadSyncRef = useRef<DirtySyncScheduler | null>(null);
  if (threadSyncRef.current === null) {
    threadSyncRef.current = new DirtySyncScheduler((threadId) => loadSelectedRef.current(threadId));
  }
  const listRefreshRef = useRef<CoalescedRefreshScheduler | null>(null);
  if (listRefreshRef.current === null) {
    listRefreshRef.current = new CoalescedRefreshScheduler(() => reloadRef.current(), 250);
  }
  const requestThreadSync = useCallback((threadId: string) => { threadSyncRef.current?.request(threadId); }, []);
  const scheduleListRefresh = useCallback(() => { listRefreshRef.current?.request(); }, []);

  useEffect(() => () => { listRefreshRef.current?.dispose(); }, []);

  useEffect(() => { void reload(); }, [reload, queue, keyword]);

  useEffect(() => {
    const fromPath = pathThreadId(pathname ?? null);
    setSelectedThreadId(fromPath);
  }, [pathname]);

  useEffect(() => {
    if (selectedThreadId) requestThreadSync(selectedThreadId);
    else void loadSelected(null);
  }, [loadSelected, requestThreadSync, selectedThreadId]);

  const handleRealtimeEvent = useCallback((event: HospitalConversationUpdatedEvent) => {
    if (!event || event.type !== "hospital.conversation.updated" || !event.thread_id) return;
    const threadId = event.thread_id;
    // 所有有效事件均静默合并刷新当前筛选下的列表与计数（Q2）。
    scheduleListRefresh();
    if (threadId === selectedThreadIdRef.current) {
      requestThreadSync(threadId);
    } else {
      // 非当前会话：不拉取正文，仅加入页面内“新消息”标记（Q3）。
      markThreadFresh(threadId);
    }
  }, [markThreadFresh, requestThreadSync, scheduleListRefresh]);

  const refreshForRecovery = useCallback(() => {
    scheduleListRefresh();
    const current = selectedThreadIdRef.current;
    if (current) requestThreadSync(current);
  }, [requestThreadSync, scheduleListRefresh]);

  const setQueue = useCallback((next: ConversationQueue) => { setQueueState(next); }, []);
  const setKeyword = useCallback((next: string) => { setKeywordState(next); }, []);

  const selectConversation = useCallback((threadId: string | null) => {
    setWriteError(null);
    setSelectedThreadId(threadId);
    // DOCTOR-WORKSPACE-000001：患者工作台内打开/关闭右侧会话抽屉，保留患者选择。
    const memberId = pathPatientMemberId(pathname ?? null);
    if (memberId !== null) {
      router.push((threadId ? `/doctor/patients/${memberId}/conversations/${encodeURIComponent(threadId)}` : `/doctor/patients/${memberId}`) as never);
      return;
    }
    router.push((threadId ? `/doctor/conversations/${encodeURIComponent(threadId)}` : "/doctor/conversations") as never);
  }, [pathname, router]);

  const handleWriteError = useCallback(async (cause: unknown, action: string, threadId: string) => {
    const resolution = resolveHospitalWriteError(cause);
    setWriteError(resolution.message);
    if (!resolution.retrySameKey) clearIdempotency(action, threadId);
    if (resolution.dropConversation) {
      dropConversation(threadId);
      return false;
    }
    if (resolution.refetchDetail) requestThreadSync(threadId);
    return false;
  }, [clearIdempotency, dropConversation, requestThreadSync]);

  const join = useCallback(async () => {
    if (!api || !selectedThreadId || !detail) return false;
    setWriteBusy(true);
    setWriteError(null);
    try {
      const binding = await api.join(selectedThreadId, detail.version, idempotencyKey("join", selectedThreadId));
      applyBinding(binding);
      clearIdempotency("join", selectedThreadId);
      requestThreadSync(selectedThreadId);
      await reload();
      return true;
    } catch (cause) {
      return handleWriteError(cause, "join", selectedThreadId);
    } finally {
      setWriteBusy(false);
    }
  }, [api, applyBinding, clearIdempotency, detail, handleWriteError, idempotencyKey, reload, requestThreadSync, selectedThreadId]);

  /** DOCTOR-WORKSPACE-000001 D-015/D-016：取消接管，恢复 AI 自动回复；不本地乐观切换。 */
  const leave = useCallback(async () => {
    if (!api || !selectedThreadId || !detail) return false;
    setWriteBusy(true);
    setWriteError(null);
    try {
      const binding = await api.leave(selectedThreadId, detail.version, idempotencyKey("leave", selectedThreadId));
      applyBinding(binding);
      clearIdempotency("leave", selectedThreadId);
      requestThreadSync(selectedThreadId);
      await reload();
      return true;
    } catch (cause) {
      return handleWriteError(cause, "leave", selectedThreadId);
    } finally {
      setWriteBusy(false);
    }
  }, [api, applyBinding, clearIdempotency, detail, handleWriteError, idempotencyKey, reload, requestThreadSync, selectedThreadId]);

  const sendMessage = useCallback(async (text: string) => {
    if (!api || !selectedThreadId || !detail) return false;
    const trimmed = text.trim();
    if (!trimmed) return false;
    setWriteBusy(true);
    setWriteError(null);
    try {
      const sent = await api.sendMessage(selectedThreadId, { text: trimmed, version: detail.version }, idempotencyKey("send", selectedThreadId));
      const local = toLocalDoctorMessage(sent, trimmed);
      let appended = false;
      setMessages((current) => {
        if (current.some((item) => item.client_message_id === sent.client_message_id || item.server_message_id === sent.server_message_id)) {
          return current;
        }
        appended = true;
        return [...current, local];
      });
      // 乐观消息登记：在服务端快照确认（稳定 ID）前不被实时快照覆盖（Q11）。
      if (appended) optimisticRef.current.set(sent.client_message_id, { threadId: selectedThreadId, message: local });
      applyBinding({ ...detail, version: sent.version, updated_at: sent.created_at });
      clearIdempotency("send", selectedThreadId);
      requestThreadSync(selectedThreadId);
      return true;
    } catch (cause) {
      return handleWriteError(cause, "send", selectedThreadId);
    } finally {
      setWriteBusy(false);
    }
  }, [api, applyBinding, clearIdempotency, detail, handleWriteError, idempotencyKey, requestThreadSync, selectedThreadId]);

  const updateAttention = useCallback(async (level: DoctorAttentionLevel, note?: string) => {
    if (!api || !selectedThreadId || !detail) return false;
    setWriteBusy(true);
    setWriteError(null);
    try {
      const binding = await api.updateAttention(
        selectedThreadId,
        { doctor_attention_level: level, attention_note: note, version: detail.version },
        idempotencyKey("attention", selectedThreadId),
      );
      applyBinding(binding);
      clearIdempotency("attention", selectedThreadId);
      await reload();
      return true;
    } catch (cause) {
      return handleWriteError(cause, "attention", selectedThreadId);
    } finally {
      setWriteBusy(false);
    }
  }, [api, applyBinding, clearIdempotency, detail, handleWriteError, idempotencyKey, reload, selectedThreadId]);

  const endConversation = useCallback(async (endReason: string) => {
    if (!api || !selectedThreadId || !detail) return false;
    setWriteBusy(true);
    setWriteError(null);
    try {
      const binding = await api.endConversation(
        selectedThreadId,
        { version: detail.version, end_reason: endReason },
        idempotencyKey("end", selectedThreadId),
      );
      applyBinding(binding);
      clearIdempotency("end", selectedThreadId);
      requestThreadSync(selectedThreadId);
      await reload();
      return true;
    } catch (cause) {
      return handleWriteError(cause, "end", selectedThreadId);
    } finally {
      setWriteBusy(false);
    }
  }, [api, applyBinding, clearIdempotency, detail, handleWriteError, idempotencyKey, reload, requestThreadSync, selectedThreadId]);

  const value = useMemo<DoctorConversationsValue>(() => ({
    status,
    detailStatus,
    error,
    detailError,
    writeError,
    writeBusy,
    queue,
    keyword,
    counts,
    cards,
    selectedThreadId,
    detail,
    messages,
    newMessageThreadIds,
    setQueue,
    setKeyword,
    reload,
    selectConversation,
    reloadSelected: () => {
      const current = selectedThreadIdRef.current;
      if (current) requestThreadSync(current);
      return Promise.resolve();
    },
    join,
    leave,
    sendMessage,
    updateAttention,
    endConversation,
    handleRealtimeEvent,
    refreshForRecovery,
  }), [
    cards, counts, detail, detailError, detailStatus, endConversation, error, handleRealtimeEvent, join, keyword,
    leave, messages, newMessageThreadIds, queue, refreshForRecovery, reload, requestThreadSync, selectConversation,
    selectedThreadId, sendMessage, setKeyword, setQueue, status, updateAttention, writeBusy, writeError,
  ]);

  return <DoctorConversationsContext.Provider value={value}>{children}</DoctorConversationsContext.Provider>;
}

export function useDoctorConversations() {
  const value = useContext(DoctorConversationsContext);
  if (!value) throw new Error("useDoctorConversations must be used inside DoctorConversationsProvider");
  return value;
}

export function useOptionalDoctorConversations() {
  return useContext(DoctorConversationsContext);
}
