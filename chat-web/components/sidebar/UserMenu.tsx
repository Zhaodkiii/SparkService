"use client";

import { useEffect, useRef, useState } from "react";
import { LogOut } from "lucide-react";
import { useOptionalAuth } from "@/context/AuthContext";

function displayName(session: { display_name?: string; email?: string } | null): string {
  const name = session?.display_name?.trim();
  if (name) return name;
  const local = session?.email?.split("@")[0];
  return local || "用户";
}

export function UserMenu() {
  const auth = useOptionalAuth();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => { window.removeEventListener("mousedown", onPointerDown); window.removeEventListener("keydown", onKeyDown); };
  }, [open]);

  if (!auth) return null;
  const name = displayName(auth.session);
  const initial = name.slice(0, 1).toUpperCase();

  return (
    <div className="sidebar-user" ref={rootRef}>
      <button type="button" className="sidebar-user__trigger" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((value) => !value)} title={name}>
        <span className="sidebar-user__avatar" aria-hidden="true">{initial}</span>
        <span className="sidebar-user__meta"><span className="sidebar__label">{name}</span></span>
      </button>
      {open && (
        <div className="sidebar-user__popover" role="menu">
          <div className="sidebar-user__popover-head">
            <span className="sidebar-user__avatar sidebar-user__avatar--lg" aria-hidden="true">{initial}</span>
            <div className="sidebar-user__popover-id">
              <strong>{name}</strong>
              {auth.session?.email ? <span>{auth.session.email}</span> : null}
            </div>
          </div>
          <button type="button" role="menuitem" onClick={() => void auth.logout()}><LogOut size={14} />退出登录</button>
        </div>
      )}
    </div>
  );
}