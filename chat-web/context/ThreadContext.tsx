"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { SparkChatSyncApi } from "@/lib/api/chat-sync-api";
import { useOptionalAuth } from "@/context/AuthContext";
import type { ChatMessageWireDTO, ChatThreadWireDTO } from "@/types/sync";
import { clientErrorDetails, sparkClientLog } from "@/lib/diagnostics";
import { sortChatMessagesForDisplay } from "@/lib/chat/message-order";

export type NewChatDraftStatus = "draft" | "materializing" | "materialized" | "failed";

export interface NewChatDraft {
  id: string;
  status: NewChatDraftStatus;
  threadId: string | null;
}

interface ThreadValue {
  status: "idle" | "loading" | "ready" | "error";
  threads: ChatThreadWireDTO[];
  messages: ChatMessageWireDTO[];
  selectedThreadId: string | null;
  error: string | null;
  draft: NewChatDraft | null;
  selectThread: (threadId: string) => void;
  startNewDraft: () => void;
  materializeDraftThread: () => Promise<string | null>;
  renameThread: (threadId: string, title: string) => Promise<boolean>;
  deleteThread: (threadId: string) => Promise<void>;
  reload: () => Promise<void>;
  reloadMessages: (threadIdOverride?: string | null) => Promise<void>;
  appendOptimisticMessage: (message: ChatMessageWireDTO) => void;
  updateMessageDelivery: (clientMessageId: string, state: ChatMessageWireDTO["delivery_state"]) => void;
}
const ThreadContext = createContext<ThreadValue | null>(null);

function newThread(title = "新对话"): ChatThreadWireDTO {
  const now = new Date().toISOString();
  return { thread_id: crypto.randomUUID(), title, scenario: "chat", is_deleted: false, updated_at: now, server_updated_at: now };
}

function pathThreadId(): string | null {
  const id = window.location.pathname.match(/\/(?:home|chat)\/([^/]+)/)?.[1];
  return id ? decodeURIComponent(id) : null;
}

function threadTimestamp(thread: ChatThreadWireDTO): number | null {
  const value = thread.server_updated_at ?? thread.updated_at;
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** 会话列表演示顺序：最新→最早（同步游标仍按 server_updated_at + id 升序）。 */
function newestThreadFirst(a: ChatThreadWireDTO, b: ChatThreadWireDTO): number {
  const aTime = threadTimestamp(a);
  const bTime = threadTimestamp(b);
  if (aTime !== null && bTime !== null && aTime !== bTime) return bTime - aTime;
  if (aTime !== null && bTime === null) return -1;
  if (aTime === null && bTime !== null) return 1;
  return a.thread_id.localeCompare(b.thread_id);
}

export function ThreadProvider({ children }: { children: React.ReactNode }) {
  const auth = useOptionalAuth();
  const router = useRouter();
  const [status, setStatus] = useState<ThreadValue["status"]>("idle");
  const [threads, setThreads] = useState<ChatThreadWireDTO[]>([]);
  const [messages, setMessages] = useState<ChatMessageWireDTO[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<NewChatDraft | null>(null);
  const materializeRef = useRef<Promise<string | null> | null>(null);

  const reload = useCallback(async () => {
    if (!auth || auth.status !== "authenticated") return;
    setStatus("loading"); setError(null);
    try {
      const api = new SparkChatSyncApi(auth.client);
      const collected: ChatThreadWireDTO[] = [];
      let cursor: string | undefined;
      let hasMore = true;
      // 服务端 thread-pull 按 server_updated_at 升序分页，只取首页会漏掉最新创建的会话；
      // 这里翻页到底后统一按“最新→最早”排序展示，保证刷新后能看到刚创建的对话。
      while (hasMore) {
        const data = await api.pullThreads(cursor, 100);
        collected.push(...data.threads.filter((thread) => !thread.is_deleted));
        cursor = data.cursor ?? undefined;
        hasMore = data.has_more;
      }
      collected.sort(newestThreadFirst);
      setThreads(collected);
      // 023：/home 永远代表新 Draft，绝不在加载后自动回退到最近 Thread。
      setSelectedThreadId((current) => (current && collected.some((thread) => thread.thread_id === current) ? current : null));
      setStatus("ready");
    } catch (cause) { setStatus("error"); setError(cause instanceof Error ? cause.message : "线程加载失败"); sparkClientLog("error", "thread.load.failed", clientErrorDetails(cause)); }
  }, [auth]);
  useEffect(() => { void reload(); }, [reload]);

  const reloadMessages = useCallback(async (threadIdOverride?: string | null) => {
    const targetThreadId = threadIdOverride ?? selectedThreadId;
    if (!auth || auth.status !== "authenticated" || !targetThreadId) {
      setMessages([]);
      return;
    }
    try {
      const data = await new SparkChatSyncApi(auth.client).pullMessages(targetThreadId, undefined, 100);
      setMessages(sortChatMessagesForDisplay(data.messages.filter((message) => !message.tombstone)));
    } catch (cause) {
      setMessages([]);
      sparkClientLog("warn", "message.history.load.failed", { thread_id: targetThreadId, ...clientErrorDetails(cause) });
    }
  }, [auth, selectedThreadId]);
  const appendOptimisticMessage = useCallback((message: ChatMessageWireDTO) => {
    setMessages((current) => current.some((item) => item.client_message_id === message.client_message_id) ? current : [...current, message]);
  }, []);
  const updateMessageDelivery = useCallback((clientMessageId: string, state: ChatMessageWireDTO["delivery_state"]) => {
    setMessages((current) => current.map((message) => message.client_message_id === clientMessageId ? { ...message, delivery_state: state } : message));
  }, []);
  useEffect(() => { void reloadMessages(); }, [reloadMessages]);

  useEffect(() => {
    const id = pathThreadId();
    if (id) { setSelectedThreadId(id); setDraft(null); }
  }, []);

  useEffect(() => {
    const onPop = () => setSelectedThreadId(pathThreadId());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const selectThread = useCallback((threadId: string) => {
    setDraft(null);
    setSelectedThreadId(threadId);
    router.push(`/home/${encodeURIComponent(threadId)}` as never);
  }, [router]);

  const startNewDraft = useCallback(() => {
    setSelectedThreadId(null);
    setMessages([]);
    setError(null);
    setDraft({ id: crypto.randomUUID(), status: "draft", threadId: null });
  }, []);

  const materializeDraftThread = useCallback(async (): Promise<string | null> => {
    if (!auth || auth.status !== "authenticated") return null;
    if (selectedThreadId) return selectedThreadId;
    if (!materializeRef.current) {
      materializeRef.current = (async () => {
        setDraft((current) => ({ id: current?.id ?? crypto.randomUUID(), status: "materializing", threadId: current?.threadId ?? null }));
        const thread = newThread("新对话");
        try {
          await new SparkChatSyncApi(auth.client).pushThreads([thread]);
        } catch (cause) {
          setDraft((current) => (current ? { ...current, status: "failed" } : current));
          sparkClientLog("error", "draft.materialize.failed", clientErrorDetails(cause));
          throw cause;
        }
        setThreads((current) => [thread, ...current]);
        setSelectedThreadId(thread.thread_id);
        setDraft((current) => ({ id: current?.id ?? thread.thread_id, status: "materialized", threadId: thread.thread_id }));
        router.push(`/home/${encodeURIComponent(thread.thread_id)}` as never);
        return thread.thread_id;
      })();
    }
    try {
      return await materializeRef.current;
    } catch {
      return null;
    } finally {
      materializeRef.current = null;
    }
  }, [auth, selectedThreadId, router]);

  const renameThread = useCallback(async (threadId: string, rawTitle: string) => {
    if (!auth || auth.status !== "authenticated") return false;
    const title = rawTitle.trim().slice(0, 120);
    const current = threads.find((thread) => thread.thread_id === threadId);
    if (!current || !title || title === current.title) return Boolean(current && title);
    const updated = { ...current, title, updated_at: new Date().toISOString() };
    setThreads((items) => items.map((thread) => thread.thread_id === threadId ? updated : thread));
    try {
      const data = await new SparkChatSyncApi(auth.client).pushThreads([updated]);
      const accepted = data.threads.find((thread) => thread.thread_id === threadId);
      if (accepted) setThreads((items) => items.map((thread) => thread.thread_id === threadId ? accepted : thread));
      return true;
    } catch (cause) {
      setThreads((items) => items.map((thread) => thread.thread_id === threadId ? current : thread));
      sparkClientLog("warn", "thread.rename.failed", { thread_id: threadId, ...clientErrorDetails(cause) });
      return false;
    }
  }, [auth, threads]);

  const deleteThread = useCallback(async (threadId: string) => {
    if (!auth) return;
    await new SparkChatSyncApi(auth.client).deleteThreads([threadId]);
    setThreads((current) => current.filter((thread) => thread.thread_id !== threadId));
    if (selectedThreadId === threadId) {
      setSelectedThreadId(null);
      startNewDraft();
      router.push("/home" as never);
    }
  }, [auth, selectedThreadId, startNewDraft, router]);

  const value = useMemo(() => ({ status, threads, messages, selectedThreadId, error, draft, selectThread, startNewDraft, materializeDraftThread, renameThread, deleteThread, reload, reloadMessages, appendOptimisticMessage, updateMessageDelivery }), [status, threads, messages, selectedThreadId, error, draft, selectThread, startNewDraft, materializeDraftThread, renameThread, deleteThread, reload, reloadMessages, appendOptimisticMessage, updateMessageDelivery]);
  return <ThreadContext.Provider value={value}>{children}</ThreadContext.Provider>;
}

export function useOptionalThreads() { return useContext(ThreadContext); }
export function useThreads() { const value = useOptionalThreads(); if (!value) throw new Error("useThreads must be used inside ThreadProvider"); return value; }
