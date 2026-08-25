import { createInitialChatRuntimeState, reduceChatEvents } from "@/lib/event-reducer";
import type { ChatEventEnvelope, ChatRuntimeState } from "@/types/chat";

export const THREAD_ID = "00000000-0000-0000-0000-000000000001";
export const RUN_ID = "00000000-0000-0000-0000-000000000010";
export const ASSISTANT_MESSAGE_ID = "1002";
export const TEXT_BLOCK_ID = "00000000-0000-0000-0000-000000000101";

const base = { run_id: RUN_ID, thread_id: THREAD_ID, payload_version: 1 } as const;

export const coherentEvents: ChatEventEnvelope[] = [
  { ...base, type: "run.queued", event_id: "00000000-0000-0000-0000-000000000011", sequence: 1, timestamp: "2026-08-25T02:00:01Z", payload: {} },
  { ...base, type: "run.started", event_id: "00000000-0000-0000-0000-000000000012", sequence: 2, timestamp: "2026-08-25T02:00:02Z", payload: {} },
  { ...base, type: "block.created", event_id: "00000000-0000-0000-0000-000000000013", sequence: 3, timestamp: "2026-08-25T02:00:03Z", payload: { message_id: ASSISTANT_MESSAGE_ID, block: { id: TEXT_BLOCK_ID, kind: "text", status: "pending", revision: 0, order_key: 1000, node_role: "timeline", payload: { text: "" } } } },
  { ...base, type: "block.delta", event_id: "00000000-0000-0000-0000-000000000014", sequence: 4, timestamp: "2026-08-25T02:00:04Z", payload: { block_id: TEXT_BLOCK_ID, revision: 1, delta: "这是一条", content_type: "text/markdown" } },
  { ...base, type: "block.delta", event_id: "00000000-0000-0000-0000-000000000015", sequence: 5, timestamp: "2026-08-25T02:00:05Z", payload: { block_id: TEXT_BLOCK_ID, revision: 2, delta: " P0 静态契约回答。", content_type: "text/markdown" } },
  { ...base, type: "block.completed", event_id: "00000000-0000-0000-0000-000000000016", sequence: 6, timestamp: "2026-08-25T02:00:06Z", payload: { block_id: TEXT_BLOCK_ID, revision: 3 } },
  { ...base, type: "run.completed", event_id: "00000000-0000-0000-0000-000000000017", sequence: 7, timestamp: "2026-08-25T02:00:07Z", payload: { terminal_status: "completed" } },
  { ...base, type: "run.done", event_id: "00000000-0000-0000-0000-000000000018", sequence: 8, timestamp: "2026-08-25T02:00:08Z", payload: { terminal_status: "completed" } },
];

export const unknownEvent: ChatEventEnvelope = { ...base, type: "future.capability.event", event_id: "00000000-0000-0000-0000-000000000019", sequence: 1, timestamp: "2026-08-25T02:00:01Z", payload: { fallback_text: "未来能力结果" } };

export const gapEvents = [coherentEvents[0], coherentEvents[2], coherentEvents[1]];

export interface ChatMessageFixture { id: string; role: "user" | "assistant"; text: string; attachment?: string; }

export const historyMessages: ChatMessageFixture[] = [
  { id: "1001", role: "user", text: "帮我看看这份健康资料应该如何开始整理？", attachment: "体检报告.pdf · 1.2 MB" },
  { id: ASSISTANT_MESSAGE_ID, role: "assistant", text: "这是一条 P0 静态契约回答。" },
];

export function stateForEvents(events: ChatEventEnvelope[] = coherentEvents): ChatRuntimeState {
  return reduceChatEvents(createInitialChatRuntimeState(), events);
}

export const emptyState = createInitialChatRuntimeState();
export const completedState = stateForEvents();
