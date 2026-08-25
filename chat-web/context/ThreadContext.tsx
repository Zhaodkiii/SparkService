"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { SparkChatSyncApi } from "@/lib/api/chat-sync-api";
import { useOptionalAuth } from "@/context/AuthContext";
import type { ChatMessageWireDTO, ChatThreadWireDTO } from "@/types/sync";
import { clientErrorDetails, sparkClientLog } from "@/lib/diagnostics";

interface ThreadValue {
  status: "idle" | "loading" | "ready" | "error";
  threads: ChatThreadWireDTO[];
  messages: ChatMessageWireDTO[];
  selectedThreadId: string | null;
  error: string | null;
  selectThread: (threadId: string) => void;
  createThread: (title?: string) => Promise<ChatThreadWireDTO | null>;
  renameThread: (threadId: string, title: string) => Promise<boolean>;
  deleteThread: (threadId: string) => Promise<void>;
  reload: () => Promise<void>;
  reloadMessages: () => Promise<void>;
}
const ThreadContext = createContext<ThreadValue | null>(null);

function newThread(title = "新对话"): ChatThreadWireDTO {
  const now = new Date().toISOString();
  return { thread_id: crypto.randomUUID(), title, scenario: "chat", is_deleted: false, updated_at: now, server_updated_at: now };
}

export function ThreadProvider({ children }: { children: React.ReactNode }) {
  const auth = useOptionalAuth();
  const [status, setStatus] = useState<ThreadValue["status"]>("idle");
  const [threads, setThreads] = useState<ChatThreadWireDTO[]>([]);
  const [messages, setMessages] = useState<ChatMessageWireDTO[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    if (!auth || auth.status !== "authenticated") return;
    setStatus("loading"); setError(null);
    try {
      const data = await new SparkChatSyncApi(auth.client).pullThreads(undefined, 100);
      setThreads(data.threads.filter((thread) => !thread.is_deleted));
      setSelectedThreadId((current) => current && data.threads.some((thread) => thread.thread_id === current) ? current : data.threads[0]?.thread_id ?? null);
      setStatus("ready");
    } catch (cause) { setStatus("error"); setError(cause instanceof Error ? cause.message : "线程加载失败"); sparkClientLog("error", "thread.load.failed", clientErrorDetails(cause)); }
  }, [auth]);
  useEffect(() => { void reload(); }, [reload]);
  const reloadMessages = useCallback(async () => {
    if (!auth || auth.status !== "authenticated" || !selectedThreadId) {
      setMessages([]);
      return;
    }
    try {
      const data = await new SparkChatSyncApi(auth.client).pullMessages(selectedThreadId, undefined, 100);
      setMessages(data.messages.filter((message) => !message.tombstone));
    } catch (cause) {
      setMessages([]);
      sparkClientLog("warn", "message.history.load.failed", { thread_id: selectedThreadId, ...clientErrorDetails(cause) });
    }
  }, [auth, selectedThreadId]);
  useEffect(() => { void reloadMessages(); }, [reloadMessages]);
  useEffect(() => {
    const id = window.location.pathname.match(/\/(?:home|chat)\/([^/]+)/)?.[1];
    if (id) setSelectedThreadId(decodeURIComponent(id));
  }, []);
  const selectThread = useCallback((threadId: string) => {
    setSelectedThreadId(threadId);
    window.history.pushState({}, "", `/home/${encodeURIComponent(threadId)}`);
  }, []);
  const createThread = useCallback(async (title?: string) => {
    if (!auth || auth.status !== "authenticated") return null;
    const thread = newThread(title);
    try { await new SparkChatSyncApi(auth.client).pushThreads([thread]); } catch { /* optimistic local thread can be retried on next reload */ }
    setThreads((current) => [thread, ...current]); setSelectedThreadId(thread.thread_id); window.history.pushState({}, "", `/home/${thread.thread_id}`); return thread;
  }, [auth]);
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
    setSelectedThreadId((current) => current === threadId ? null : current);
    if (selectedThreadId === threadId) window.history.pushState({}, "", "/home");
  }, [auth, selectedThreadId]);
  const value = useMemo(() => ({ status, threads, messages, selectedThreadId, error, selectThread, createThread, renameThread, deleteThread, reload, reloadMessages }), [status, threads, messages, selectedThreadId, error, selectThread, createThread, renameThread, deleteThread, reload, reloadMessages]);
  return <ThreadContext.Provider value={value}>{children}</ThreadContext.Provider>;
}

export function useOptionalThreads() { return useContext(ThreadContext); }
export function useThreads() { const value = useOptionalThreads(); if (!value) throw new Error("useThreads must be used inside ThreadProvider"); return value; }
