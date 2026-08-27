import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AssistantTurn } from "@/components/chat/turn/AssistantTurn";
import type { ChatBlockDTO } from "@/types/chat";

function block(overrides: Partial<ChatBlockDTO> & { id: string; kind: string }): ChatBlockDTO {
  return {
    status: "ready",
    revision: 1,
    order_key: 1,
    node_role: "timeline",
    payload: {},
    ...overrides,
  };
}

describe("AssistantTurn", () => {
  it("does not render a fixed assistant avatar", () => {
    const { container } = render(
      <AssistantTurn
        messageId="m1"
        blocks={[block({ id: "t", kind: "text", payload: { text: { _0: "你好" } } })]}
        turnSummary={{ run_id: "r1", status: "completed", started_at: "2026-08-26T00:00:00Z", finished_at: "2026-08-26T00:00:08Z", duration_ms: 8000, regenerate_allowed: true, delete_allowed: true, usage: null }}
      />,
    );
    expect(container.querySelector(".message__avatar")).toBeNull();
    expect(container.querySelectorAll(".turn-activity__state").length).toBe(1);
    expect(container.textContent).toContain("已完成");
  });
});
