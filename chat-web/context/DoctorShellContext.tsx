"use client";

import { createContext, useContext } from "react";

interface DoctorShellValue {
  collapsed: boolean;
  mobileOpen: boolean;
  openSidebar: () => void;
  closeSidebar: () => void;
}

const DoctorShellContext = createContext<DoctorShellValue | null>(null);

export function DoctorShellProvider({ value, children }: { value: DoctorShellValue; children: React.ReactNode }) {
  return <DoctorShellContext.Provider value={value}>{children}</DoctorShellContext.Provider>;
}

export function useDoctorShell() {
  const value = useContext(DoctorShellContext);
  if (!value) throw new Error("useDoctorShell must be used inside DoctorAppShell");
  return value;
}

export function useOptionalDoctorShell() {
  return useContext(DoctorShellContext);
}
