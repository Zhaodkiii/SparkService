import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssistantResponse } from "@/components/chat/turn/AssistantResponse";
import type { ChatBlockDTO } from "@/types/chat";

// React.memo objects expose their custom comparator as `.compare`. Testing it
// directly is more deterministic than counting Profiler commits, since a
// Profiler still fires an "update" entry for a commit even when every child
// bails out via memo (it reflects the render pass reaching that boundary,
// not whether the wrapped function component itself was re-invoked).
type MemoComponent<P> = { compare: (prev: P, next: P) => boolean };

function memoCompare<P>(component: unknown, prev: P, next: P): boolean {
  return (component as MemoComponent<P>).compare(prev, next);
}

function textBlock(overrides: Partial<ChatBlockDTO> & { id: string }): ChatBlockDTO {
  return {
    status: "ready",
    revision: 1,
    order_key: 1,
    node_role: "timeline",
    kind: "text",
    payload: {},
    ...overrides,
  } as ChatBlockDTO;
}

let matchMediaReduced = false;

beforeEach(() => {
  vi.stubGlobal("matchMedia", (query: string) =>
    ({
      matches: matchMediaReduced,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }) as unknown as MediaQueryList,
  );
});

afterEach(() => {
  matchMediaReduced = false;
  vi.unstubAllGlobals();
});

describe("AssistantResponse", () => {
  it("renders the full text immediately under prefers-reduced-motion, even while streaming", () => {
    matchMediaReduced = true;
    const block = textBlock({ id: "b1", status: "streaming", revision: 3 });
    const { container } = render(<AssistantResponse block={block} text="完整的最终答案" />);
    expect(container.textContent).toContain("完整的最终答案");
  });

  it("treats a completed block as unchanged when only the object identity differs (skip re-render)", () => {
    const prev = { block: textBlock({ id: "b2", status: "ready", revision: 5 }), text: "已完成的回答" };
    // A brand-new `block` object (as the parent would produce on every render)
    // but with identical id/status/revision and the same text.
    const next = { block: textBlock({ id: "b2", status: "ready", revision: 5 }), text: "已完成的回答" };
    expect(prev.block).not.toBe(next.block);
    expect(memoCompare(AssistantResponse, prev, next)).toBe(true);
  });

  it("re-renders when the block advances to a new revision", () => {
    const prev = { block: textBlock({ id: "b3", status: "streaming", revision: 1 }), text: "第 1 版" };
    const next = { block: textBlock({ id: "b3", status: "streaming", revision: 2 }), text: "第 2 版" };
    expect(memoCompare(AssistantResponse, prev, next)).toBe(false);
  });

  it("re-renders when only status changes (e.g. streaming -> ready) even if text is unchanged", () => {
    const prev = { block: textBlock({ id: "b4", status: "streaming", revision: 1 }), text: "内容" };
    const next = { block: textBlock({ id: "b4", status: "ready", revision: 1 }), text: "内容" };
    expect(memoCompare(AssistantResponse, prev, next)).toBe(false);
  });
});
