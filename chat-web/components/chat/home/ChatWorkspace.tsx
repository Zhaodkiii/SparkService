"use client";

import { useMemo, useRef, useState } from "react";
import { ChatComposer } from "@/components/chat/home/ChatComposer";
import { ChatHeader } from "@/components/chat/home/ChatHeader";
import { ChatMessages } from "@/components/chat/home/ChatMessages";
import { SessionActivityPanel } from "@/components/chat/home/SessionActivityPanel";
import { useOptionalRunControl } from "@/context/RunControlContext";
import { useOptionalThreads } from "@/context/ThreadContext";
import { useChatAutoScroll } from "@/hooks/useChatAutoScroll";

export function ChatWorkspace() {
  const [activityOpen, setActivityOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const run = useOptionalRunControl();
  const threads = useOptionalThreads();
  const scrollDependency = useMemo(() => `${threads?.messages.length ?? 0}:${Object.values(run?.state.blocksById ?? {}).map((block) => `${block.id}:${block.revision}`).join("|")}`, [run?.state.blocksById, threads?.messages.length]);
  useChatAutoScroll(scrollRef, scrollDependency);
  return <div className="chat-workspace">
    <ChatHeader activityOpen={activityOpen} onToggleActivity={() => setActivityOpen((value) => !value)} />
    <div className="chat-scroll" data-chat-scroll-root ref={scrollRef}>
      <section className="message-column"><ChatMessages /></section>
    </div>
    <div className="composer-wrap"><ChatComposer /></div>
    <SessionActivityPanel open={activityOpen} onClose={() => setActivityOpen(false)} />
  </div>;
}
