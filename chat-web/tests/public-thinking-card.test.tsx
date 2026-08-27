import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PublicThinkingCard } from "@/components/chat/turn/PublicThinkingCard";
import type { ChatBlockDTO } from "@/types/chat";

function thinkingBlock(overrides: Partial<ChatBlockDTO> = {}): ChatBlockDTO {
  return {
    id: "think_1",
    kind: "deepThought",
    status: "ready",
    revision: 1,
    order_key: 1,
    node_role: "timeline",
    payload: { deep_thought: { _0: { summary: "已排查过敏史与用药记录" } } },
    ...overrides,
  };
}

describe("PublicThinkingCard", () => {
  it("returns null for a block with no public summary text", () => {
    const { container } = render(<PublicThinkingCard block={thinkingBlock({ payload: { deep_thought: { _0: {} } } })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("reads reasoning_content from the canonical deepThought payload", () => {
    render(<PublicThinkingCard block={thinkingBlock({ payload: { deep_thought: { _0: { reasoning_content: "正在分析睡眠数据" } } } })} />);
    expect(screen.getByText("正在分析睡眠数据")).toBeInTheDocument();
  });

  it("stays expanded while the block is still streaming", () => {
    render(<PublicThinkingCard block={thinkingBlock({ status: "streaming" })} />);
    const details = document.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(true);
  });

  it("auto-collapses once the block settles to ready", () => {
    render(<PublicThinkingCard block={thinkingBlock({ status: "ready" })} />);
    const details = document.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
  });

  it("respects a manual user toggle over the auto-collapse default", () => {
    render(<PublicThinkingCard block={thinkingBlock({ status: "ready" })} />);
    const details = document.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    fireEvent.click(screen.getByText("思考"));
    expect(details.open).toBe(true);
  });
});
