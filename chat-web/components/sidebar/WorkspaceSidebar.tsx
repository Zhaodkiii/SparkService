"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { Activity, BookOpen, Brain, ChevronDown, Dumbbell, HeartPulse, Home, MoreHorizontal, Pencil, Settings, Trash2, Utensils } from "lucide-react";
import { useChatRuntime } from "@/context/ChatRuntimeContext";
import { useOptionalThreads } from "@/context/ThreadContext";
import { useOptionalRunControl } from "@/context/RunControlContext";
import { SidebarShell } from "@/components/sidebar/SidebarShell";

const PRIMARY_NAV = [
  { href: "/home", label: "主页", icon: Home }, { href: "/medical", label: "医疗", icon: HeartPulse },
  { href: "/nutrition", label: "饮食", icon: Utensils }, { href: "/exercise", label: "运动", icon: Dumbbell },
] as const;
const BOTTOM_NAV = [
  { href: "/knowledge", label: "知识库", icon: BookOpen }, { href: "/memory", label: "记忆", icon: Brain },
  { href: "/settings", label: "设置", icon: Settings },
] as const;

export function WorkspaceSidebar({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const { scenario } = useChatRuntime();
  const threads = useOptionalThreads();
  const runControl = useOptionalRunControl();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState("");
  const [menuId, setMenuId] = useState<string | null>(null);
  const finishRename = async (threadId: string) => { const accepted = await threads?.renameThread(threadId, titleDraft); if (accepted) setEditingId(null); };

  const handleHomeNewChat = async () => {
    const settled = runControl ? await runControl.settleActiveRun() : true;
    if (!settled) return;
    threads?.startNewDraft();
    router.push("/home" as never);
    onNavigate?.();
  };

  return <SidebarShell collapsed={collapsed}>
    <div className="sidebar__top">
      <button className="sidebar__brand" onClick={() => void handleHomeNewChat()} aria-label="小鲸健康 AI 主页"><span className="brand-mark">鲸</span><span className="sidebar__label">小鲸健康</span></button>
    </div>
    <nav className="sidebar__nav" aria-label="全局导航">
      {PRIMARY_NAV.map(({ href, label, icon: Icon }) => { const active = pathname === href || pathname.startsWith(`${href}/`); return href === "/home" ? <button key={href} className="sidebar-nav-item" aria-current={active ? "page" : undefined} onClick={() => void handleHomeNewChat()} title={label}><Icon size={16} strokeWidth={active ? 1.9 : 1.55} /><span className="sidebar__label">{label}</span></button> : <Link key={href} href={href as never} className="sidebar-nav-item" aria-current={active ? "page" : undefined} onClick={onNavigate} title={label}><Icon size={16} strokeWidth={active ? 1.9 : 1.55} /><span className="sidebar__label">{label}</span></Link>; })}
    </nav>
    <section className="sidebar__sessions" aria-label="对话记录">
      <div className="sidebar__section-title"><span className="sidebar__label">最近对话</span><ChevronDown size={13} /></div>
      {threads?.error && <p className="sidebar__notice" role="alert">对话加载失败</p>}
      <ul className="thread-list">
        {threads ? threads.threads.map((thread) => <li className="thread-row" key={thread.thread_id}>
          {editingId === thread.thread_id && !collapsed ? <form className="thread-rename" onSubmit={(event) => { event.preventDefault(); void finishRename(thread.thread_id); }}><input autoFocus value={titleDraft} maxLength={120} aria-label="对话名称" onChange={(event) => setTitleDraft(event.target.value)} onBlur={() => void finishRename(thread.thread_id)} /></form> : <button className="thread-item" aria-current={threads.selectedThreadId === thread.thread_id ? "true" : undefined} onClick={() => { threads.selectThread(thread.thread_id); onNavigate?.(); }} title={thread.title || "新对话"}><Activity size={14} /><span className="sidebar__label">{thread.title || "新对话"}</span></button>}
          {!collapsed && <button className="thread-more" type="button" aria-label={`${thread.title || "新对话"}操作`} aria-expanded={menuId === thread.thread_id} onClick={() => setMenuId((value) => value === thread.thread_id ? null : thread.thread_id)}><MoreHorizontal size={15} /></button>}
          {menuId === thread.thread_id && !collapsed && <div className="thread-menu"><button type="button" onClick={() => { setTitleDraft(thread.title || "新对话"); setEditingId(thread.thread_id); setMenuId(null); }}><Pencil size={14} />重命名</button><button className="thread-menu__danger" type="button" onClick={() => { setMenuId(null); void threads.deleteThread(thread.thread_id); }}><Trash2 size={14} />删除</button></div>}
        </li>) : <><li><button className="thread-item" aria-current={scenario !== "empty" ? "true" : undefined}><Activity size={14} /><span className="sidebar__label">体检资料整理</span></button></li><li><button className="thread-item"><Activity size={14} /><span className="sidebar__label">睡眠质量改善建议</span></button></li></>}
        {threads?.status === "ready" && threads.threads.length === 0 && !collapsed && <li className="sidebar__notice">暂无历史对话</li>}
      </ul>
    </section>
    <nav className="sidebar__bottom" aria-label="资源与设置">
      {BOTTOM_NAV.map(({ href, label, icon: Icon }) => { const active = pathname === href || pathname.startsWith(`${href}/`); return <Link key={href} href={href as never} className="sidebar-nav-item" aria-current={active ? "page" : undefined} onClick={onNavigate} title={label}><Icon size={16} /><span className="sidebar__label">{label}</span></Link>; })}
      <div className="sidebar__version"><span className="sidebar__label">Spark AI · Web</span></div>
    </nav>
  </SidebarShell>;
}
