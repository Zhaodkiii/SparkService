"use client";
/* eslint-disable react-hooks/refs */

import { useEffect, useMemo, useRef } from "react";
import { SparkApiError } from "@/lib/api/http-client";
import { SparkHospitalApi } from "@/lib/api/hospital-api";
import { useOptionalAuth } from "@/context/AuthContext";
import { useOptionalDoctorConversations } from "@/context/DoctorConversationsContext";
import { useOptionalDoctorRealtimeStatus } from "@/context/DoctorRealtimeStatusContext";
import { useOptionalPatientWorkspace } from "@/context/PatientWorkspaceContext";
import { doctorConversationWebSocketUrl, isHospitalConversationUpdatedEvent, realtimeRetryDelay } from "@/lib/hospital/realtime";

/** BACKOFFICE-CONVERSATION-000002 §8.3.1：医生工作台实时连接管理。
 *
 *  - 认证完成后申请一次性 ticket 并建立医生会话 WebSocket。
 *  - 建连/重连成功后执行一次合并补偿刷新（Q5）。
 *  - 网络错误指数退避重连（1s→…→30s + 抖动）；页面不可见时暂停，
 *    重新可见或 online 时立即重连；4401/4403 与 ticket 401/403 不无限重连。
 *  - 事件只携带变化提示；诊断仅记录关联元数据，不打印消息对象（Q9）。
 *  - 组件卸载、退出登录（布局卸载）时关闭连接并清理定时器。
 */
export function DoctorRealtimeBridge() {
  const auth = useOptionalAuth();
  const conversations = useOptionalDoctorConversations();
  const patientWorkspace = useOptionalPatientWorkspace();
  const realtimeStatus = useOptionalDoctorRealtimeStatus();
  const api = useMemo(() => (auth ? new SparkHospitalApi(auth.client) : null), [auth]);

  // DOCTOR-WORKSPACE-000004 第 15 问：向工作台广播连接状态（断线禁发/提示）。
  const reportStatusRef = useRef(realtimeStatus?.report);
  reportStatusRef.current = realtimeStatus?.report;

  // 通过 ref 调用最新的会话处理器，避免 context value 变化导致 WebSocket 反复重建。
  const handleEventRef = useRef(conversations?.handleRealtimeEvent);
  const refreshRef = useRef(conversations?.refreshForRecovery);
  handleEventRef.current = conversations?.handleRealtimeEvent;
  refreshRef.current = conversations?.refreshForRecovery;
  // DOCTOR-WORKSPACE-000001：同一实时事件同步驱动患者列表与患者模块合并刷新。
  const patientHandleRef = useRef(patientWorkspace?.handleRealtimeEvent);
  const patientRefreshRef = useRef(patientWorkspace?.refreshForRecovery);
  patientHandleRef.current = patientWorkspace?.handleRealtimeEvent;
  patientRefreshRef.current = patientWorkspace?.refreshForRecovery;

  // 注意：effect 依赖只允许使用稳定标量。conversations 的 context value 在每次
  // 消息/列表/计数更新后都会变更引用，若作为依赖会导致 建连→补偿刷新→状态更新→
  // value 变更→重连 的死循环（日志表现为 ws-tickets 每秒多次）。
  const conversationsReady = conversations !== null;

  useEffect(() => {
    if (!api || auth?.status !== "authenticated" || !conversationsReady) return;
    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;
    let attempt = 0;

    const clearRetry = () => {
      if (retryTimer !== null) {
        window.clearTimeout(retryTimer);
        retryTimer = null;
      }
    };

    const scheduleRetry = () => {
      if (disposed) return;
      // 浏览器不可见时不持续高频重连，等待 visibilitychange/online 触发。
      if (document.visibilityState === "hidden") return;
      reportStatusRef.current?.("disconnected");
      const delay = realtimeRetryDelay(attempt) + Math.floor(Math.random() * 300);
      attempt += 1;
      retryTimer = window.setTimeout(() => void connect(), delay);
    };

    const connect = async () => {
      if (disposed) return;
      clearRetry();
      try {
        const ticket = await api.createConversationWebSocketTicket();
        if (disposed) return;
        socket = new WebSocket(doctorConversationWebSocketUrl(ticket.websocket_path, ticket.ticket));
        socket.onopen = () => {
          attempt = 0;
          reportStatusRef.current?.("connected");
          // 建连/重连成功：合并补偿刷新列表、计数与当前会话（Q5）。
          refreshRef.current?.();
          patientRefreshRef.current?.();
        };
        socket.onmessage = (message) => {
          try {
            const data = JSON.parse(String(message.data)) as unknown;
            if (isHospitalConversationUpdatedEvent(data)) {
              handleEventRef.current?.(data);
              patientHandleRef.current?.(data);
            }
          } catch {
            // 无法解析的帧直接忽略；REST 补偿仍是最终事实源。
          }
        };
        socket.onerror = () => socket?.close();
        socket.onclose = (event) => {
          socket = null;
          if (disposed) return;
          // 认证失败、医生身份失效不做无限重连；等待登录状态或页面可见性变化。
          if (event.code === 4401 || event.code === 4403) {
            console.info("[doctor-realtime] closed by server", { code: event.code });
            reportStatusRef.current?.("failed");
            return;
          }
          scheduleRetry();
        };
      } catch (cause) {
        if (disposed) return;
        if (cause instanceof SparkApiError && (cause.failure.httpStatus === 401 || cause.failure.httpStatus === 403)) {
          console.info("[doctor-realtime] ticket rejected", { status: cause.failure.httpStatus });
          reportStatusRef.current?.("failed");
          return;
        }
        scheduleRetry();
      }
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        attempt = 0;
        void connect();
      }
    };
    const onOnline = () => {
      attempt = 0;
      void connect();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("online", onOnline);
    void connect();

    return () => {
      disposed = true;
      clearRetry();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("online", onOnline);
      socket?.close(1000, "doctor realtime disposed");
    };
  }, [api, auth?.status, conversationsReady]);

  return null;
}
