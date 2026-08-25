"use client";

import { createContext, useContext, useMemo, useState } from "react";
import { coherentEvents, emptyState, gapEvents, historyMessages, stateForEvents, unknownEvent } from "@/fixtures/chat/scenarios";
import { reduceChatEvents } from "@/lib/event-reducer";
import type { ChatRuntimeState } from "@/types/chat";

export type FixtureScenario = "empty" | "history" | "streaming" | "gap" | "unknown" | "offline" | "forbidden";

interface ChatRuntimeValue {
  scenario: FixtureScenario;
  setScenario: (scenario: FixtureScenario) => void;
  state: ChatRuntimeState;
  history: typeof historyMessages;
  offline: boolean;
  forbidden: boolean;
}

const ChatRuntimeContext = createContext<ChatRuntimeValue | null>(null);

export function ChatRuntimeProvider({ children, initialScenario = "history" }: { children: React.ReactNode; initialScenario?: FixtureScenario }) {
  const [scenario, setScenario] = useState<FixtureScenario>(initialScenario);
  const state = useMemo(() => {
    if (scenario === "empty" || scenario === "offline" || scenario === "forbidden") return emptyState;
    if (scenario === "gap") return stateForEvents(gapEvents);
    if (scenario === "unknown") return stateForEvents([unknownEvent]);
    if (scenario === "streaming") return stateForEvents(coherentEvents.slice(0, 5));
    return stateForEvents();
  }, [scenario]);
  const value = useMemo(() => ({ scenario, setScenario, state, history: historyMessages, offline: scenario === "offline", forbidden: scenario === "forbidden" }), [scenario, state]);
  return <ChatRuntimeContext.Provider value={value}>{children}</ChatRuntimeContext.Provider>;
}

export function useChatRuntime(): ChatRuntimeValue {
  const value = useContext(ChatRuntimeContext);
  if (!value) throw new Error("useChatRuntime must be used inside ChatRuntimeProvider");
  return value;
}
