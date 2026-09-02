"use client";

import { useState } from "react";
import { ChevronLeft, PanelRight, Star } from "lucide-react";
import { useOptionalDoctorShell } from "@/context/DoctorShellContext";
import { useDoctorConversations } from "@/context/DoctorConversationsContext";
import { ATTENTION_LABEL, SERVICE_STATUS_LABEL, relativeTime } from "@/lib/hospital/labels";
import type { DoctorAttentionLevel } from "@/types/hospital";

const ATTENTION_OPTIONS: DoctorAttentionLevel[] = ["normal", "follow_up", "priority"];

export function DoctorConversationHeader({ panelOpen, onTogglePanel }: { panelOpen: boolean; onTogglePanel: () => void }) {
  const conversations = useDoctorConversations();
  const shell = useOptionalDoctorShell();
  const detail = conversations.detail;
  const [pickerOpen, setPickerOpen] = useState(false);
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
        <div className="doctor-attention-wrap">
          <button
            className={`doctor-attention-button${detail.doctor_attention_level === "priority" ? " doctor-attention-button--on" : ""}`}
            type="button"
            aria-expanded={pickerOpen}
            disabled={conversations.writeBusy || detail.service_status === "ended"}
            onClick={() => setPickerOpen((value) => !value)}
          >
            <Star size={14} />
            {detail.doctor_attention_level === "normal" ? "关注" : ATTENTION_LABEL[detail.doctor_attention_level]}
          </button>
          {pickerOpen && (
            <div className="doctor-attention-menu" role="menu">
              {ATTENTION_OPTIONS.map((level) => (
                <button
                  key={level}
                  type="button"
                  role="menuitem"
                  aria-current={detail.doctor_attention_level === level}
                  onClick={() => { setPickerOpen(false); void conversations.updateAttention(level, detail.attention_note); }}
                >
                  {ATTENTION_LABEL[level]}
                </button>
              ))}
            </div>
          )}
        </div>
        <button className="icon-button" type="button" aria-label="患者资料" aria-pressed={panelOpen} title="患者资料" onClick={onTogglePanel}>
          <PanelRight size={16} />
        </button>
      </div>
    </header>
  );
}
