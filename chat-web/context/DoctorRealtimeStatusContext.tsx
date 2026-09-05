"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

/** DOCTOR-WORKSPACE-000004 第 15 问：医生工作台实时连接状态。
 *
 * - connecting：首次连接或退避重连中；
 * - connected：实时通道可用；
 * - disconnected：连接已断开（自动重连进行中），发送必须禁用；
 * - failed：ticket/身份失效等不可恢复错误，停止重连并引导重新进入。
 */
export type DoctorRealtimeStatus = "connecting" | "connected" | "disconnected" | "failed";

interface DoctorRealtimeStatusValue {
  status: DoctorRealtimeStatus;
  report: (status: DoctorRealtimeStatus) => void;
}

const DoctorRealtimeStatusContext = createContext<DoctorRealtimeStatusValue | null>(null);

export function DoctorRealtimeStatusProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<DoctorRealtimeStatus>("connecting");
  const report = useCallback((next: DoctorRealtimeStatus) => {
    setStatus((current) => (current === next ? current : next));
  }, []);
  const value = useMemo(() => ({ status, report }), [status, report]);
  return <DoctorRealtimeStatusContext.Provider value={value}>{children}</DoctorRealtimeStatusContext.Provider>;
}

export function useDoctorRealtimeStatus(): DoctorRealtimeStatusValue {
  const value = useContext(DoctorRealtimeStatusContext);
  if (!value) throw new Error("useDoctorRealtimeStatus must be used inside DoctorRealtimeStatusProvider");
  return value;
}

export function useOptionalDoctorRealtimeStatus(): DoctorRealtimeStatusValue | null {
  return useContext(DoctorRealtimeStatusContext);
}
