"use client";

import { ChevronLeft, PanelRight } from "lucide-react";
import { useOptionalDoctorShell } from "@/context/DoctorShellContext";
import { useDoctorConversations } from "@/context/DoctorConversationsContext";
import { SERVICE_STATUS_LABEL, relativeTime } from "@/lib/hospital/labels";

export function DoctorConversationHeader({ panelOpen, onTogglePanel }: { panelOpen: boolean; onTogglePanel: () => void }) {
  const conversations = useDoctorConversations();
  const shell = useOptionalDoctorShell();
  const detail = conversations.detail;
  if (!detail) return null;

  return (
    <header className="chat-header doctor-header">
      <button className="doctor-header__back" type="button" aria-label="返回会话列表" onClick={() => { conversations.selectConversation(null); shell?.openSidebar(); }}>
        <ChevronLeft size={18} />
      </button>
      <button className="doctor-header__list" type="button" aria-label="打开会话列表" onClick={() => shell?.openSidebar()}>
        会话列表
      </button>
      <div className="chat-header__title-wrap">
        <h1 className="doctor-header__title">{detail.patient_display_name || "患者"} · {detail.department.short_name || detail.department.name}</h1>
        <p className="doctor-header__sub">
          {detail.agent.name} · {SERVICE_STATUS_LABEL[detail.service_status]}
          {detail.updated_at ? ` · 更新于 ${relativeTime(detail.updated_at)}` : ""}
        </p>
      </div>
      <div className="chat-header__actions">
        <button className="icon-button" type="button" aria-label="患者资料" aria-pressed={panelOpen} title="患者资料" onClick={onTogglePanel}>
          <PanelRight size={16} />
        </button>
      </div>
    </header>
  );
}
