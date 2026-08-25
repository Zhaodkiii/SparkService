"use client";

import { useEffect, useState } from "react";
import { Menu, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { WorkspaceSidebar } from "@/components/sidebar/WorkspaceSidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  useEffect(() => {
    if (!mobileOpen) return;
    const close = (event: KeyboardEvent) => event.key === "Escape" && setMobileOpen(false);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [mobileOpen]);
  return <div className={`app-shell${collapsed ? " app-shell--collapsed" : ""}`}>
    <button className="mobile-menu-button" type="button" aria-label="打开侧边栏" onClick={() => setMobileOpen(true)}><Menu size={19} /></button>
    {mobileOpen && <button className="sidebar-scrim" type="button" aria-label="关闭侧边栏" onClick={() => setMobileOpen(false)} />}
    <div className={`sidebar-frame${mobileOpen ? " sidebar-frame--open" : ""}`}>
      <WorkspaceSidebar collapsed={collapsed} onNavigate={() => setMobileOpen(false)} />
      <button className="sidebar-mobile-close" type="button" aria-label="关闭侧边栏" onClick={() => setMobileOpen(false)}><X size={18} /></button>
      <button className="sidebar-collapse" type="button" aria-label={collapsed ? "展开侧边栏" : "收起侧边栏"} onClick={() => setCollapsed((value) => !value)}>{collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}</button>
    </div>
    <main className="workspace">{children}</main>
  </div>;
}
