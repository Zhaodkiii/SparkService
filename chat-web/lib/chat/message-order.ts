import type { ChatMessageWireDTO } from "@/types/sync";

const ROLE_ORDER: Record<ChatMessageWireDTO["role"], number> = {
  system: 0,
  user: 1,
  assistant: 2,
};

function timestamp(value: string | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Conversation display order; sync cursors use server_updated_at + id. */
export function compareChatMessages(a: ChatMessageWireDTO, b: ChatMessageWireDTO): number {
  const aTime = timestamp(a.created_at);
  const bTime = timestamp(b.created_at);
  if (aTime !== null && bTime !== null && aTime !== bTime) return aTime - bTime;
  if (aTime !== null && bTime === null) return -1;
  if (aTime === null && bTime !== null) return 1;

  const roleDelta = ROLE_ORDER[a.role] - ROLE_ORDER[b.role];
  if (roleDelta !== 0) return roleDelta;

  const aId = a.server_message_id || a.client_message_id;
  const bId = b.server_message_id || b.client_message_id;
  return aId.localeCompare(bId);
}

export function sortChatMessagesForDisplay(messages: ChatMessageWireDTO[]): ChatMessageWireDTO[] {
  return [...messages].sort(compareChatMessages);
}
