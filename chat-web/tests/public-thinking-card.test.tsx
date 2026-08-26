import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PublicThinkingCard } from "@/components/chat/turn/PublicThinkingCard";
import type { ChatBlockDTO } from "@/types/chat";

const flagState = vi.hoisted(() => ({ deepTutorUiEnabled: false }));
vi.mock("@/lib/feature-flags", () => ({
  get CHAT_DEEPTUTOR_TURN_UI_ENABLED() { return flagState.deepTutorUiEnabled; },
  CHAT_SMOOTH_STREAM_ENABLED: false,
  CHAT_TOOL_UI_ENABLED: false,
  CHAT_TOOL_SETTINGS_ENABLED: false,
}));

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

afterEach(() => {
  flagState.deepTutorUiEnabled = false;
});

describe("PublicThinkingCard — legacy renderer (flag off)", () => {
  it("renders a plain static card without a details/summary shell", () => {
    render(<PublicThinkingCard block={thinkingBlock()} />);
    expect(screen.getByText("已排查过敏史与用药记录")).toBeInTheDocument();
    expect(document.querySelector("details")).toBeFalsy();
  });

  it("returns null for a block with no public summary text", () => {
    const { container } = render(<PublicThinkingCard block={thinkingBlock({ payload: { deep_thought: { _0: {} } } })} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("PublicThinkingCard — DeepTutor renderer (flag on)", () => {
  it("stays expanded while the block is still streaming", () => {
    flagState.deepTutorUiEnabled = true;
    render(<PublicThinkingCard block={thinkingBlock({ status: "streaming" })} />);
    const details = document.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(true);
  });

  it("auto-collapses once the block settles to ready", () => {
    flagState.deepTutorUiEnabled = true;
    render(<PublicThinkingCard block={thinkingBlock({ status: "ready" })} />);
    const details = document.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
  });

  it("respects a manual user toggle over the auto-collapse default", () => {
    flagState.deepTutorUiEnabled = true;
    render(<PublicThinkingCard block={thinkingBlock({ status: "ready" })} />);
    const details = document.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    fireEvent.click(screen.getByText("思考"));
    expect(details.open).toBe(true);
  });
});
