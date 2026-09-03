"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Bot, ClipboardList, LogOut, MessageSquare, Search, Star } from "lucide-react";
import { SidebarShell } from "@/components/sidebar/SidebarShell";
import { useAuth } from "@/context/AuthContext";
import { useDoctorAuth } from "@/context/DoctorAuthGate";
import { useDoctorConversations } from "@/context/DoctorConversationsContext";
import { ATTENTION_LABEL, QUEUE_LABEL, RISK_LABEL, SERVICE_STATUS_LABEL, relativeTime } from "@/lib/hospital/labels";
import type { ConversationQueue } from "@/types/hospital";

const NAV = [
  { href: "/doctor/conversations", label: "会话工作台", icon: MessageSquare },
  { href: "/doctor/agent", label: "我的智能体", icon: Bot },
  { href: "/doctor/work-logs", label: "工作记录", icon: ClipboardList },
] as const;

const QUEUES = ["all", "pending", "priority", "ended"] as const satisfies readonly ConversationQueue[];

export function DoctorSidebar({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const pathname = usePathname() ?? "";
  const auth = useAuth();
  const { hospital, doctor } = useDoctorAuth();
  const conversations = useDoctorConversations();
  const { setKeyword } = conversations;
  const [search, setSearch] = useState(conversations.keyword);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setKeyword(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search, setKeyword]);

  const initial = (doctor.display_name || "医").slice(0, 1);
  const conversationsActive = pathname === "/doctor/conversations" || pathname.startsWith("/doctor/conversations/");

  return (
    <SidebarShell collapsed={collapsed}>
      <div className="sidebar__top">
        <Link href={"/doctor/conversations" as never} className="sidebar__brand" onClick={onNavigate} aria-label={`${hospital.short_name || hospital.name} 医生工作台`}>
          <span className="brand-mark">{(hospital.short_name || hospital.name).slice(0, 1)}</span>
          <span className="sidebar__label">
            <strong>{hospital.short_name || hospital.name}</strong>
            <em className="doctor-brand-sub">医生工作台</em>
          </span>
        </Link>
      </div>
      <nav className="sidebar__nav" aria-label="医生工作台导航">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/doctor/conversations" ? conversationsActive : pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link key={href} href={href as never} className="sidebar-nav-item" aria-current={active ? "page" : undefined} onClick={onNavigate} title={label}>
              <Icon size={16} strokeWidth={active ? 1.9 : 1.55} />
              <span className="sidebar__label">{label}</span>
            </Link>
          );
        })}
      </nav>
      <section className="sidebar__sessions doctor-sidebar-sessions" aria-label="患者会话">
        <label className="sidebar-search doctor-sidebar-search">
          <Search size={13} />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索患者或会话…" aria-label="搜索患者或会话" />
        </label>
        <div className="doctor-queue-tabs" role="tablist" aria-label="会话筛选">
          {QUEUES.map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={conversations.queue === item}
              className="doctor-queue-tab"
              onClick={() => conversations.setQueue(item)}
            >
              <span className="sidebar__label">{QUEUE_LABEL[item]}</span>
              <em>{conversations.counts[item]}</em>
            </button>
          ))}
        </div>
        {conversations.error && (
          <p className="sidebar__notice" role="alert">
            会话加载失败
            <button type="button" className="doctor-inline-retry" onClick={() => void conversations.reload()}>重试</button>
          </p>
        )}
        {conversations.status === "loading" && !conversations.cards.length && <p className="sidebar__notice">正在加载会话…</p>}
        <ul className="thread-list doctor-card-list">
          {conversations.cards.map((card) => {
            const selected = conversations.selectedThreadId === card.thread_id;
            // BACKOFFICE-CONVERSATION-000002 Q3：非当前会话收到实时事件后的页面内“新消息”标记，
            // 成功读取该会话后由 context 清除；刷新页面后允许消失。
            const fresh = !selected && conversations.newMessageThreadIds.includes(card.thread_id);
            return (
              <li key={card.thread_id}>
                <button
                  type="button"
                  className="doctor-card"
                  aria-current={selected ? "true" : undefined}
                  onClick={() => { conversations.selectConversation(card.thread_id); onNavigate?.(); }}
                >
                  <div className="doctor-card__title">
                    {card.doctor_attention_level === "priority" && <Star size={12} className="doctor-card__star" aria-label={ATTENTION_LABEL.priority} />}
                    <span className="sidebar__label">{card.patient_display_name || "患者"}</span>
                    {fresh && <i className="doctor-card__fresh" role="img" aria-label="新消息" title="新消息" />}
                    {card.unread_count > 0 && <b className="doctor-card__unread" aria-label={`${card.unread_count} 条未读`}>{card.unread_count}</b>}
                  </div>
                  <div className="doctor-card__tags sidebar__label">
                    {card.risk_signal_level !== "none" && <span className={`doctor-tag doctor-tag--risk-${card.risk_signal_level}`}>{RISK_LABEL[card.risk_signal_level]}</span>}
                    <span className={`doctor-tag doctor-tag--status-${card.service_status}`}>{SERVICE_STATUS_LABEL[card.service_status]}</span>
                  </div>
                  <p className="doctor-card__preview sidebar__label">{card.title || "暂无摘要"}</p>
                  <p className="doctor-card__meta sidebar__label">{card.department.short_name || card.department.name} · {relativeTime(card.updated_at)}</p>
                </button>
              </li>
            );
          })}
          {conversations.status === "ready" && conversations.cards.length === 0 && !collapsed && (
            <li className="sidebar__notice">当前筛选暂无会话</li>
          )}
        </ul>
      </section>
      <div className="sidebar__bottom">
        <div className="sidebar-user">
          <button type="button" className="sidebar-user__trigger" aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((value) => !value)} title={`${doctor.display_name} · ${doctor.title}`}>
            <span className="sidebar-user__avatar" aria-hidden="true">{initial}</span>
            <span className="sidebar-user__meta">
              <span className="sidebar__label">{doctor.display_name}{doctor.title ? ` · ${doctor.title}` : ""}</span>
            </span>
          </button>
          {menuOpen && (
            <div className="sidebar-user__popover" role="menu">
              <div className="sidebar-user__popover-head">
                <span className="sidebar-user__avatar sidebar-user__avatar--lg" aria-hidden="true">{initial}</span>
                <div className="sidebar-user__popover-id">
                  <strong>{doctor.display_name}</strong>
                  <span>{hospital.name}</span>
                  {doctor.title ? <span>{doctor.title}</span> : null}
                </div>
              </div>
              <button type="button" role="menuitem" onClick={() => void auth.logout()}><LogOut size={14} />退出登录</button>
            </div>
          )}
        </div>
      </div>
    </SidebarShell>
  );
}
