"use client";

import { useMemo, useRef, useState } from "react";
import { HeartPulse } from "lucide-react";
import { DoctorComposer } from "@/components/doctor/DoctorComposer";
import { DoctorConversationHeader } from "@/components/doctor/DoctorConversationHeader";
import { DoctorConversationPanel } from "@/components/doctor/DoctorConversationPanel";
import { DoctorMessages } from "@/components/doctor/DoctorMessages";
import { useDoctorConversations } from "@/context/DoctorConversationsContext";
import { useChatAutoScroll } from "@/hooks/useChatAutoScroll";

export function DoctorConversationWorkspace() {
  const conversations = useDoctorConversations();
  const [panelOpen, setPanelOpen] = useState(false);
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const scrollDependency = useMemo(
    () => `${conversations.messages.length}:${conversations.detail?.version ?? 0}:${conversations.detailStatus}`,
    [conversations.detail?.version, conversations.detailStatus, conversations.messages.length],
  );
  useChatAutoScroll(scrollRef, scrollDependency);

  if (!conversations.selectedThreadId) {
    return (
      <div className="chat-workspace doctor-workspace">
        <div className="empty-state">
          <div className="empty-state__mark"><HeartPulse size={22} /></div>
          <div>
            <p className="empty-state__eyebrow">医生会话工作台</p>
            <h1>选择一位患者开始处理</h1>
            <p>从左侧查看待接管、重点关注和进行中的患者会话。</p>
            <div className="prompt-suggestions">
              <span>今日待接管 {conversations.counts.pending}</span>
              <span>重点关注 {conversations.counts.priority}</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-workspace doctor-workspace">
      <DoctorConversationHeader panelOpen={panelOpen} onTogglePanel={() => setPanelOpen((value) => !value)} />
      <div className="chat-scroll" data-chat-scroll-root ref={scrollRef}>
        <section className="message-column">
          <DoctorMessages highlightId={highlightId} />
        </section>
      </div>
      <div className="composer-wrap"><DoctorComposer /></div>
      <DoctorConversationPanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        onJumpToRisk={(messageId) => {
          setHighlightId(messageId);
          setPanelOpen(false);
          window.requestAnimationFrame(() => {
            document.getElementById(`doctor-msg-${messageId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
          });
        }}
      />
    </div>
  );
}
