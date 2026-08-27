"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useOptionalAuth } from "@/context/AuthContext";
import { useOptionalThreads } from "@/context/ThreadContext";
import { SparkRunApi } from "@/lib/api/run-api";
import { SparkInteractionApi } from "@/lib/api/interaction-api";
import { createInitialChatRuntimeState, reduceChatEvents, upsertInteractions } from "@/lib/event-reducer";
import { isTerminalRunStatus } from "@/types/chat";
import type { ChatEventEnvelope, ChatRunDTO, ChatRunStatus, ChatRuntimeState } from "@/types/chat";
import type { CreateTurnContextInput } from "@/types/context";
import type { ChatMessageWireDTO } from "@/types/sync";
import type { InteractionSubmitBody } from "@/types/interaction";
import { clientErrorDetails, sparkClientLog } from "@/lib/diagnostics";
import { SparkApiError, userFacingApiError } from "@/lib/api/http-client";

type ConnectionState = "idle" | "connecting" | "live" | "replaying" | "polling";

type InteractionCommandOutcome = { ok: true } | { ok: false; error: string; httpStatus?: number; code?: number };

interface RunValue {
  run: ChatRunDTO | null;
  events: ChatEventEnvelope[];
  state: ChatRuntimeState;
  connectionState: ConnectionState;
  busy: boolean;
  error: string | null;
  createRun: (content: string, context?: CreateTurnContextInput | null, overrideThreadId?: string | null) => Promise<boolean>;
  cancelRun: () => Promise<boolean>;
  regenerate: () => Promise<void>;
  settleActiveRun: () => Promise<boolean>;
  refreshPending: (runId: string) => Promise<void>;
  submitInteraction: (interactionId: string, body: InteractionSubmitBody) => Promise<InteractionCommandOutcome>;
  refuseInteraction: (interactionId: string, reason?: string) => Promise<InteractionCommandOutcome>;
}

const RunContext = createContext<RunValue | null>(null);

function applyRunPatch(
  current: ChatRunDTO | null,
  patch: { id: string; thread_id?: string; status: string; last_sequence?: number },
): ChatRunDTO | null {
  if (!current || current.id !== patch.id) return current;
  return {
    ...current,
    status: patch.status as ChatRunStatus,
    last_sequence: patch.last_sequence ?? current.last_sequence,
    ...(patch.thread_id ? { thread_id: patch.thread_id } : {}),
  };
}

function websocketUrl(path: string, ticket: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const configuredBase = process.env.NEXT_PUBLIC_SPARK_WS_BASE_URL;
  const url = new URL(path, configuredBase || `${protocol}//${window.location.host}`);
  url.searchParams.set("ticket", ticket);
  return url.toString();
}

function statusFromEvent(event: ChatEventEnvelope): ChatRunDTO["status"] | null {
  const statuses: Record<string, ChatRunDTO["status"]> = {
    "run.queued": "queued",
    "run.started": "running",
  };
  if (event.type === "run.done") {
    const terminal = String((event.payload as Record<string, unknown>)?.terminal_status ?? "");
    if (["completed", "failed", "cancelled", "interrupted"].includes(terminal)) return terminal as ChatRunDTO["status"];
  }
  if (event.type === "run.waiting") {
    const waiting = String((event.payload as Record<string, unknown>)?.status ?? "");
    if (waiting === "waiting_for_user_input" || waiting === "waiting_for_client_tool") return waiting;
  }
  if (event.type === "run.resumed" || event.type === "run.queued") return "queued";
  return statuses[event.type] ?? null;
}

export function RunControlProvider({ children }: { children: React.ReactNode }) {
  const auth = useOptionalAuth();
  const threads = useOptionalThreads();
  const threadId = threads?.selectedThreadId ?? null;
  const [run, setRun] = useState<ChatRunDTO | null>(null);
  const [events, setEvents] = useState<ChatEventEnvelope[]>([]);
  const [state, setState] = useState<ChatRuntimeState>(createInitialChatRuntimeState);
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastSequenceRef = useRef<Record<string, number>>({});
  const api = useMemo(() => auth ? new SparkRunApi(auth.client) : null, [auth]);
  const interactionApi = useMemo(() => auth ? new SparkInteractionApi(auth.client) : null, [auth]);
  const activeRunId = run?.id ?? null;
  const activeRunStatus = run?.status ?? null;
  const reloadMessages = threads?.reloadMessages;

  const applyEvents = useCallback((incoming: ChatEventEnvelope[]) => {
    if (!incoming.length) return;
    setEvents((current) => {
      const seen = new Set(current.map((event) => event.event_id));
      return [...current, ...incoming.filter((event) => !seen.has(event.event_id))];
    });
    setState((current) => {
      const next = reduceChatEvents(current, incoming);
      lastSequenceRef.current = { ...lastSequenceRef.current, ...next.lastAppliedSequenceByRun };
      for (const event of incoming) sparkClientLog("info", "run.event.applied", { run_id: event.run_id, event_type: event.type, sequence: event.sequence });
      return next;
    });
  }, []);

  useEffect(() => {
    if (!run) return;
    const done = events.find((event) => event.run_id === run.id && event.type === "run.done");
    if (!done || (state.lastAppliedSequenceByRun[run.id] ?? 0) < done.sequence) return;
    const status = statusFromEvent(done);
    if (status) setRun((current) => {
      if (!current || current.id !== run.id || (current.status === status && current.last_sequence >= done.sequence)) return current;
      return { ...current, status, last_sequence: Math.max(current.last_sequence, done.sequence) };
    });
  }, [events, run, state.lastAppliedSequenceByRun]);

  useEffect(() => {
    if (!run) return;
    const projected = state.runsById[run.id];
    if (!projected?.status || projected.status === run.status) return;
    setRun((current) => {
      if (!current || current.id !== run.id || current.status === projected.status) return current;
      return { ...current, status: projected.status, last_sequence: Math.max(current.last_sequence, projected.last_sequence) };
    });
  }, [run, state.runsById]);

  const replay = useCallback(async (runId: string, after?: number) => {
    if (!api) return;
    try {
      let cursor = after ?? lastSequenceRef.current[runId] ?? 0;
      for (let page = 0; page < 20; page += 1) {
        const data = await api.events(runId, cursor, 200);
        applyEvents(data.events);
        cursor = data.next_after_sequence;
        if (!data.has_more) break;
      }
    } catch (cause) {
      sparkClientLog("warn", "run.replay.failed", { run_id: runId, ...clientErrorDetails(cause) });
      throw cause;
    }
  }, [api, applyEvents]);

  const refreshPending = useCallback(async (runId: string) => {
    if (!interactionApi || !runId) return;
    try {
      const data = await interactionApi.getPendingForRun(runId);
      setState((current) => upsertInteractions(current, runId, data.interactions ?? []));
    } catch (cause) {
      sparkClientLog("warn", "interaction.pending_lookup.failed", { run_id: runId, ...clientErrorDetails(cause) });
    }
  }, [interactionApi]);

  const refresh = useCallback(async () => {
    if (!api || !threadId || auth?.status !== "authenticated") return;
    try {
      const result = await api.getActive(threadId);
      setRun(result.run);
      setState(createInitialChatRuntimeState());
      setEvents([]);
      lastSequenceRef.current = {};
      if (result.run) {
        await replay(result.run.id, 0);
        if (result.run.status === "waiting_for_user_input" || result.run.status === "waiting_for_client_tool") {
          await refreshPending(result.run.id);
        }
      }
    } catch {
      sparkClientLog("warn", "run.active_lookup.failed", { thread_id: threadId });
      setRun(null);
    }
  }, [api, auth?.status, refreshPending, replay, threadId]);

  useEffect(() => {
    setRun(null);
    setState(createInitialChatRuntimeState());
    setEvents([]);
    lastSequenceRef.current = {};
    void refresh();
  }, [threadId, refresh]);

  useEffect(() => {
    if (!api || !activeRunId || !activeRunStatus || isTerminalRunStatus(activeRunStatus) || auth?.status !== "authenticated") {
      setConnectionState("idle");
      return;
    }
    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;

    const connect = async (attempt: number) => {
      if (disposed) return;
      setConnectionState("connecting");
      try {
        const ticket = await api.createWebSocketTicket();
        if (disposed) return;
        socket = new WebSocket(websocketUrl(ticket.websocket_path, ticket.ticket));
        sparkClientLog("info", "run.ws.connecting", { run_id: activeRunId, attempt });
        socket.onopen = () => {
          if (disposed || !socket) return;
          setConnectionState("live");
          sparkClientLog("info", "run.ws.connected", { run_id: activeRunId, attempt });
          socket.send(JSON.stringify({ type: "run.subscribe", run_id: activeRunId, after_sequence: lastSequenceRef.current[activeRunId] ?? 0 }));
        };
        socket.onmessage = (message) => {
          try {
            const event = JSON.parse(String(message.data)) as ChatEventEnvelope;
            if (event.event_id && event.run_id === activeRunId && Number.isInteger(event.sequence)) applyEvents([event]);
          } catch {
            // Protocol control messages and malformed payloads do not alter projections.
          }
        };
        socket.onclose = (event: CloseEvent) => {
          if (disposed) return;
          // 019G：服务端以 4401 关闭 = 鉴权失败（ticket 无效/过期且刷新已失败）。
          // 停止无限重连，等待用户重新登录后再恢复。
          if (event.code === 4401) {
            setConnectionState("idle");
            sparkClientLog("warn", "run.ws.auth_rejected", { run_id: activeRunId, attempt, close_code: event.code, source: "ws_auth" });
            return;
          }
          setConnectionState("polling");
          sparkClientLog("warn", "run.ws.closed", { run_id: activeRunId, attempt, close_code: event.code });
          const delay = Math.min(10_000, 500 * (2 ** Math.min(attempt, 5)));
          retryTimer = window.setTimeout(() => void connect(attempt + 1), delay);
        };
        socket.onerror = () => socket?.close();
      } catch (cause) {
        // 019G：ticket 申请 401 且自动刷新失败 → 鉴权来源失败，停止重连。
        if (cause instanceof SparkApiError && cause.failure.httpStatus === 401) {
          setConnectionState("idle");
          sparkClientLog("warn", "run.ws.ticket_auth_failed", { run_id: activeRunId, attempt, source: "ticket_auth", ...clientErrorDetails(cause) });
          return;
        }
        sparkClientLog("warn", "run.ws.connection_failed", { run_id: activeRunId, attempt, ...clientErrorDetails(cause) });
        if (!disposed) {
          setConnectionState("polling");
          retryTimer = window.setTimeout(() => void connect(attempt + 1), Math.min(10_000, 500 * (2 ** Math.min(attempt, 5))));
        }
      }
    };
    void connect(0);
    return () => {
      disposed = true;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      socket?.close(1000, "run changed");
    };
  }, [activeRunId, activeRunStatus, api, applyEvents, auth?.status]);

  useEffect(() => {
    if (!api || !run || isTerminalRunStatus(run.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const result = await api.get(run.id);
        setRun(result.run);
        await replay(run.id);
      } catch {
        setConnectionState("polling");
      }
    }, connectionState === "live" ? 10_000 : 2_000);
    return () => window.clearInterval(timer);
  }, [api, connectionState, replay, run]);

  useEffect(() => {
    if (!run || !state.replayRequiredByRun[run.id]) return;
    void replay(run.id);
  }, [replay, run, state.replayRequiredByRun]);

  const createRun = useCallback(async (content: string, context?: CreateTurnContextInput | null, overrideThreadId?: string | null) => {
    const targetThreadId = overrideThreadId ?? threadId;
    if (!api || !targetThreadId || !content.trim()) return false;
    const clientMessageId = crypto.randomUUID();
    const optimisticMessage: ChatMessageWireDTO = {
      thread_id: targetThreadId, role: "user", client_message_id: clientMessageId, server_message_id: null,
      delivery_state: "sending", created_at: new Date().toISOString(), server_updated_at: null, tombstone: false,
      attachments: context?.attachments ?? [],
      blocks: [{ id: crypto.randomUUID(), kind: "text", status: "ready", revision: 1, order_key: 1000, node_role: "timeline", payload: { text: { _0: content.trim() } } }],
    };
    threads?.appendOptimisticMessage(optimisticMessage);
    setBusy(true);
    setError(null);
    try {
      const data = await api.create(targetThreadId, {
        input_message: {
          thread_id: targetThreadId,
          role: "user",
          client_message_id: clientMessageId,
          blocks: [
            {
              kind: "text",
              status: "ready",
              revision: 1,
              order_key: 1000,
              node_role: "timeline",
              payload: { text: { _0: content.trim() } },
            },
          ],
        },
        run_options: {
          capability: "chat",
          preferences_revision: context?.preferencesRevision,
          context_parent_message_id: context?.contextParentMessageId,
          context_inputs: context?.references ?? [],
          attachments: context?.attachments ?? [],
          client: { platform: "web", version: "p3", device_id: "web" },
        },
      }, crypto.randomUUID());
      setRun(data.run);
      setState(createInitialChatRuntimeState());
      setEvents([]);
      lastSequenceRef.current = {};
      await replay(data.run.id, 0);
      await threads?.reloadMessages(targetThreadId);
      return true;
    } catch (cause) {
      const message = cause instanceof SparkApiError ? userFacingApiError(cause.failure) : cause instanceof Error ? cause.message : "创建 Run 失败";
      sparkClientLog("error", "run.create.failed", { thread_id: targetThreadId, ...clientErrorDetails(cause) });
      threads?.updateMessageDelivery(clientMessageId, "failed");
      setError(message);
      return false;
    } finally {
      setBusy(false);
    }
  }, [api, replay, threadId, threads]);

  const cancelRun = useCallback(async () => {
    if (!api || !run) return false;
    setBusy(true);
    try {
      const data = await api.cancel(run.id);
      setRun(data.run);
      await replay(run.id);
      return true;
    } catch (cause) {
      setError(cause instanceof SparkApiError ? userFacingApiError(cause.failure) : cause instanceof Error ? cause.message : "取消失败");
      sparkClientLog("error", "run.cancel.failed", { run_id: run.id, ...clientErrorDetails(cause) });
      return false;
    } finally {
      setBusy(false);
    }
  }, [api, replay, run]);

  const settleActiveRun = useCallback(async (): Promise<boolean> => {
    if (!run || isTerminalRunStatus(run.status)) return true;
    return cancelRun();
  }, [run, cancelRun]);

  const regenerate = useCallback(async () => {
    if (!api || !run) return;
    setBusy(true);
    try {
      const data = await api.regenerate(run.id, crypto.randomUUID());
      setRun(data.run);
      setState(createInitialChatRuntimeState());
      setEvents([]);
      lastSequenceRef.current = {};
      await replay(data.run.id, 0);
    } catch (cause) {
      setError(cause instanceof SparkApiError ? userFacingApiError(cause.failure) : cause instanceof Error ? cause.message : "重新生成失败");
      sparkClientLog("error", "run.regenerate.failed", { run_id: run.id, ...clientErrorDetails(cause) });
    } finally {
      setBusy(false);
    }
  }, [api, replay, run]);

  useEffect(() => {
    if (activeRunStatus && isTerminalRunStatus(activeRunStatus)) void reloadMessages?.();
  }, [activeRunStatus, reloadMessages]);

  useEffect(() => {
    if (!activeRunId || (activeRunStatus !== "waiting_for_user_input" && activeRunStatus !== "waiting_for_client_tool")) return;
    void refreshPending(activeRunId);
  }, [activeRunId, activeRunStatus, refreshPending]);

  const recoverInteraction = useCallback(async (runId: string, interactionId: string) => {
    if (!interactionApi) return;
    try {
      const fresh = await interactionApi.get(interactionId);
      setState((current) => upsertInteractions(current, runId, [fresh.interaction]));
    } catch (cause) {
      sparkClientLog("warn", "interaction.refresh.failed", { run_id: runId, interaction_id: interactionId, ...clientErrorDetails(cause) });
    }
    await replay(runId);
    await refreshPending(runId);
  }, [interactionApi, refreshPending, replay]);

  const submitInteraction = useCallback(async (interactionId: string, body: InteractionSubmitBody): Promise<InteractionCommandOutcome> => {
    if (!interactionApi || !run) return { ok: false, error: "当前无法提交" };
    try {
      const data = await interactionApi.submitResponse(interactionId, body, crypto.randomUUID());
      if (data.run) setRun((current) => applyRunPatch(current, data.run));
      if (data.interaction) setState((current) => upsertInteractions(current, run.id, [data.interaction]));
      await replay(run.id);
      return { ok: true };
    } catch (cause) {
      if (cause instanceof SparkApiError && (cause.failure.httpStatus === 409 || cause.failure.httpStatus === 410)) {
        await recoverInteraction(run.id, interactionId);
        return { ok: false, error: userFacingApiError(cause.failure), httpStatus: cause.failure.httpStatus, code: cause.failure.code };
      }
      const error = cause instanceof SparkApiError ? userFacingApiError(cause.failure) : cause instanceof Error ? cause.message : "提交失败";
      sparkClientLog("warn", "interaction.submit.failed", { run_id: run.id, interaction_id: interactionId, ...clientErrorDetails(cause) });
      return { ok: false, error };
    }
  }, [interactionApi, recoverInteraction, replay, run]);

  const refuseInteraction = useCallback(async (interactionId: string, reason = "user_refused"): Promise<InteractionCommandOutcome> => {
    if (!interactionApi || !run) return { ok: false, error: "当前无法跳过" };
    try {
      const data = await interactionApi.refuse(interactionId, reason, crypto.randomUUID());
      if (data.run) setRun((current) => applyRunPatch(current, data.run));
      if (data.interaction) setState((current) => upsertInteractions(current, run.id, [data.interaction]));
      await replay(run.id);
      return { ok: true };
    } catch (cause) {
      if (cause instanceof SparkApiError && (cause.failure.httpStatus === 409 || cause.failure.httpStatus === 410)) {
        await recoverInteraction(run.id, interactionId);
        return { ok: false, error: userFacingApiError(cause.failure), httpStatus: cause.failure.httpStatus, code: cause.failure.code };
      }
      const error = cause instanceof SparkApiError ? userFacingApiError(cause.failure) : cause instanceof Error ? cause.message : "跳过失败";
      return { ok: false, error };
    }
  }, [interactionApi, recoverInteraction, replay, run]);

  const value = useMemo(() => ({ run, events, state, connectionState, busy, error, createRun, cancelRun, regenerate, settleActiveRun, refreshPending, submitInteraction, refuseInteraction }), [run, events, state, connectionState, busy, error, createRun, cancelRun, regenerate, settleActiveRun, refreshPending, submitInteraction, refuseInteraction]);
  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useOptionalRunControl() { return useContext(RunContext); }
export function useRunControl() {
  const value = useOptionalRunControl();
  if (!value) throw new Error("useRunControl must be used inside RunControlProvider");
  return value;
}
