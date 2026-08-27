import { describe, expect, it } from "vitest";
import { compareChatMessages, sortChatMessagesForDisplay } from "@/lib/chat/message-order";
import type { ChatMessageWireDTO } from "@/types/sync";

function message(role: ChatMessageWireDTO["role"], id: string, createdAt = "2026-08-26T09:32:32.000Z"): ChatMessageWireDTO {
  return {
    thread_id: "thread",
    role,
    client_message_id: `${id}-client`,
    server_message_id: `${id}-server`,
    delivery_state: "sent",
    created_at: createdAt,
    blocks: [],
  };
}

describe("message display order", () => {
  it("orders same-time messages as system, user, assistant", () => {
    const input = [message("assistant", "a"), message("user", "u"), message("system", "s")];
    expect(sortChatMessagesForDisplay(input).map((item) => item.role)).toEqual(["system", "user", "assistant"]);
  });

  it("orders by created_at before same-time fallbacks", () => {
    const earlier = message("assistant", "earlier", "2026-08-26T09:32:31.999999Z");
    const later = message("user", "later", "2026-08-26T09:32:32.000001Z");
    expect(compareChatMessages(earlier, later)).toBeLessThan(0);
  });
});
