"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useOptionalAuth } from "@/context/AuthContext";
import { useOptionalThreads } from "@/context/ThreadContext";
import { SparkApiError } from "@/lib/api/http-client";
import { SparkContextApi } from "@/lib/api/context-api";
import { addTurnContextItem, emptyTurnContextDraft, removeTurnContextItem, toCreateTurnContextInput } from "@/lib/context/turn-context-draft";
import type { CreateTurnContextInput, ThreadPreferencesDTO, TurnContextDraft, TurnContextItem } from "@/types/context";

interface ChatContextValue {
  preferences: ThreadPreferencesDTO | null;
  draft: TurnContextDraft;
  status: "idle" | "loading" | "ready" | "saving" | "conflict" | "error";
  error: string | null;
  updatePreferences: (patch: Partial<ThreadPreferencesDTO>) => Promise<boolean>;
  addItem: (item: TurnContextItem) => void;
  removeItem: (key: string) => void;
  clearDraft: () => void;
  createTurnContext: () => CreateTurnContextInput | null;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatContextProvider({ children }: { children: React.ReactNode }) {
  const auth = useOptionalAuth();
  const threads = useOptionalThreads();
  const threadId = threads?.selectedThreadId ?? null;
  const [preferences, setPreferences] = useState<ThreadPreferencesDTO | null>(null);
  const [draft, setDraft] = useState<TurnContextDraft>(() => emptyTurnContextDraft(threadId));
  const [status, setStatus] = useState<ChatContextValue["status"]>("idle");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!auth || auth.status !== "authenticated" || !threadId) {
      setPreferences(null); setDraft(emptyTurnContextDraft(threadId)); setStatus("idle"); return;
    }
    setStatus("loading"); setError(null);
    try {
      const data = await new SparkContextApi(auth.client).getPreferences(threadId);
      setPreferences(data); setDraft(emptyTurnContextDraft(threadId)); setStatus("ready");
    } catch (cause) { setStatus("error"); setError(cause instanceof Error ? cause.message : "上下文配置加载失败"); }
  }, [auth, threadId]);

  useEffect(() => { void load(); }, [load]);

  const updatePreferences = useCallback(async (patch: Partial<ThreadPreferencesDTO>) => {
    if (!auth || !threadId || !preferences) return false;
    setStatus("saving"); setError(null);
    try {
      const data = await new SparkContextApi(auth.client).updatePreferences(threadId, preferences.revision, patch);
      setPreferences(data); setStatus("ready"); return true;
    } catch (cause) {
      const conflict = cause instanceof SparkApiError && cause.failure.code === 40993;
      setStatus(conflict ? "conflict" : "error");
      setError(conflict ? "此对话已在其他窗口更新，请刷新后确认最新设置。" : "上下文配置保存失败"); return false;
    }
  }, [auth, preferences, threadId]);

  const addItem = useCallback((item: TurnContextItem) => setDraft((current) => addTurnContextItem(current, item)), []);
  const removeItem = useCallback((key: string) => setDraft((current) => removeTurnContextItem(current, key)), []);
  const clearDraft = useCallback(() => setDraft(emptyTurnContextDraft(threadId)), [threadId]);
  const createTurnContext = useCallback(() => preferences ? toCreateTurnContextInput(draft, preferences.revision) : null, [draft, preferences]);
  const value = useMemo(() => ({ preferences, draft, status, error, updatePreferences, addItem, removeItem, clearDraft, createTurnContext }), [preferences, draft, status, error, updatePreferences, addItem, removeItem, clearDraft, createTurnContext]);
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useOptionalChatContext() { return useContext(ChatContext); }
export function useChatContext() { const value = useOptionalChatContext(); if (!value) throw new Error("useChatContext must be used inside ChatContextProvider"); return value; }
