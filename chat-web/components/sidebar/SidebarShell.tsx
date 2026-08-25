"use client";

export function SidebarShell({ children, collapsed = false }: { children: React.ReactNode; collapsed?: boolean }) {
  return <aside className="sidebar" aria-label="会话侧栏" data-collapsed={collapsed || undefined}>{children}</aside>;
}
