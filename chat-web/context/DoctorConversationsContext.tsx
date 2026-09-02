"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { SparkHospitalApi, toLocalDoctorMessage } from "@/lib/api/hospital-api";
import { useOptionalAuth } from "@/context/AuthContext";
import { hospitalErrorMessage, newIdempotencyKey } from "@/lib/hospital/errors";
import { resolveHospitalWriteError } from "@/lib/hospital/write-result";
import type {
  ConversationCardDTO,
  ConversationDetailDTO,
  ConversationQueue,
  ConversationQueueCounts,
  DoctorAttentionLevel,
  DoctorMessageDTO,
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
  setQueue: (queue: ConversationQueue) => void;
  setKeyword: (keyword: string) => void;
  reload: () => Promise<void>;
  selectConversation: (threadId: string | null) => void;
  reloadSelected: () => Promise<void>;
  join: () => Promise<boolean>;
  sendMessage: (text: string) => Promise<boolean>;
  updateAttention: (level: DoctorAttentionLevel, note?: string) => Promise<boolean>;
  endConversation: (endReason: string) => Promise<boolean>;
}

const DoctorConversationsContext = createContext<DoctorConversationsValue | null>(null);

function pathThreadId(pathname: string | null): string | null {
  const match = (pathname ?? "").match(/\/doctor\/conversations\/([^/]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
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
  const idempotencyRef = useRef<Record<string, string>>({});
  const queueRef = useRef(queue);
  const keywordRef = useRef(keyword);
  queueRef.current = queue;
  keywordRef.current = keyword;

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
    if (selectedThreadId === threadId) {
      setSelectedThreadId(null);
      router.push("/doctor/conversations" as never);
    }
  }, [router, selectedThreadId]);

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
      setDetail(nextDetail);
      setMessages(nextMessages.items);
      setCards((current) => current.map((card) => (card.thread_id === nextDetail.thread_id ? { ...card, ...nextDetail } : card)));
      setDetailStatus("ready");
    } catch (cause) {
      const resolution = resolveHospitalWriteError(cause);
      if (resolution.dropConversation) {
        dropConversation(threadId);
        setWriteError(resolution.message);
        setDetailStatus("idle");
        return;
      }
      setDetailStatus("error");
      setDetailError(hospitalErrorMessage(cause));
    }
  }, [api, auth?.status, dropConversation]);

  useEffect(() => { void reload(); }, [reload, queue, keyword]);

  useEffect(() => {
    const fromPath = pathThreadId(pathname ?? null);
    setSelectedThreadId(fromPath);
  }, [pathname]);

  useEffect(() => { void loadSelected(selectedThreadId); }, [loadSelected, selectedThreadId]);

  const setQueue = useCallback((next: ConversationQueue) => { setQueueState(next); }, []);
  const setKeyword = useCallback((next: string) => { setKeywordState(next); }, []);

  const selectConversation = useCallback((threadId: string | null) => {
    setWriteError(null);
    setSelectedThreadId(threadId);
    router.push((threadId ? `/doctor/conversations/${encodeURIComponent(threadId)}` : "/doctor/conversations") as never);
  }, [router]);

  const handleWriteError = useCallback(async (cause: unknown, action: string, threadId: string) => {
    const resolution = resolveHospitalWriteError(cause);
    setWriteError(resolution.message);
    if (!resolution.retrySameKey) clearIdempotency(action, threadId);
    if (resolution.dropConversation) {
      dropConversation(threadId);
      return false;
    }
    if (resolution.refetchDetail) await loadSelected(threadId);
    return false;
  }, [clearIdempotency, dropConversation, loadSelected]);

  const join = useCallback(async () => {
    if (!api || !selectedThreadId || !detail) return false;
    setWriteBusy(true);
    setWriteError(null);
    try {
      const binding = await api.join(selectedThreadId, detail.version, idempotencyKey("join", selectedThreadId));
      applyBinding(binding);
      clearIdempotency("join", selectedThreadId);
      await Promise.all([loadSelected(selectedThreadId), reload()]);
      return true;
    } catch (cause) {
      return handleWriteError(cause, "join", selectedThreadId);
    } finally {
      setWriteBusy(false);
    }
  }, [api, applyBinding, clearIdempotency, detail, handleWriteError, idempotencyKey, loadSelected, reload, selectedThreadId]);

  const sendMessage = useCallback(async (text: string) => {
    if (!api || !selectedThreadId || !detail) return false;
    const trimmed = text.trim();
    if (!trimmed) return false;
    setWriteBusy(true);
    setWriteError(null);
    try {
      const sent = await api.sendMessage(selectedThreadId, { text: trimmed, version: detail.version }, idempotencyKey("send", selectedThreadId));
      setMessages((current) => {
        if (current.some((item) => item.client_message_id === sent.client_message_id || item.server_message_id === sent.server_message_id)) {
          return current;
        }
        return [...current, toLocalDoctorMessage(sent, trimmed)];
      });
      applyBinding({ ...detail, version: sent.version, updated_at: sent.created_at });
      clearIdempotency("send", selectedThreadId);
      await loadSelected(selectedThreadId);
      return true;
    } catch (cause) {
      return handleWriteError(cause, "send", selectedThreadId);
    } finally {
      setWriteBusy(false);
    }
  }, [api, applyBinding, clearIdempotency, detail, handleWriteError, idempotencyKey, loadSelected, selectedThreadId]);

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
      await Promise.all([loadSelected(selectedThreadId), reload()]);
      return true;
    } catch (cause) {
      return handleWriteError(cause, "end", selectedThreadId);
    } finally {
      setWriteBusy(false);
    }
  }, [api, applyBinding, clearIdempotency, detail, handleWriteError, idempotencyKey, loadSelected, reload, selectedThreadId]);

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
    setQueue,
    setKeyword,
    reload,
    selectConversation,
    reloadSelected: () => loadSelected(selectedThreadId),
    join,
    sendMessage,
    updateAttention,
    endConversation,
  }), [
    cards, counts, detail, detailError, detailStatus, endConversation, error, join, keyword, loadSelected,
    messages, queue, reload, selectConversation, selectedThreadId, sendMessage, setKeyword, setQueue,
    status, updateAttention, writeBusy, writeError,
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
