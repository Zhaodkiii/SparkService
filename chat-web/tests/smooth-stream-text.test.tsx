import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSmoothStreamText } from "@/hooks/useSmoothStreamText";

// CHAT-WEB-027 W2: migrated alongside useSmoothStreamText.ts from DeepTutor
// Web's test of the same hook (Apache-2.0, see THIRD_PARTY_NOTICES.md),
// adapted to this repo's fake-rAF harness instead of DeepTutor's.
let frameQueue: { id: number; cb: FrameRequestCallback }[] = [];
let nextFrameId = 0;

function flushFrame() {
  const queue = frameQueue;
  frameQueue = [];
  act(() => {
    queue.forEach(({ cb }) => cb(performance.now()));
  });
}

beforeEach(() => {
  frameQueue = [];
  nextFrameId = 0;
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    nextFrameId += 1;
    frameQueue.push({ id: nextFrameId, cb });
    return nextFrameId;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => {
    frameQueue = frameQueue.filter((entry) => entry.id !== id);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useSmoothStreamText", () => {
  it("reveals growing content progressively across frames instead of jumping to the full string", () => {
    const { result, rerender } = renderHook(
      ({ content, isStreaming }: { content: string; isStreaming: boolean }) =>
        useSmoothStreamText(content, isStreaming, { maxCharsPerFrame: 5, minCharsPerFrame: 1, catchUpDivisor: 5 }),
      { initialProps: { content: "", isStreaming: true } },
    );
    expect(result.current).toBe("");

    rerender({ content: "0123456789", isStreaming: true });
    flushFrame();
    expect(result.current.length).toBeGreaterThan(0);
    expect(result.current.length).toBeLessThan(10);

    for (let i = 0; i < 20 && result.current !== "0123456789"; i += 1) {
      flushFrame();
    }
    expect(result.current).toBe("0123456789");
  });

  it("shrinks immediately when the canonical content becomes shorter", () => {
    const { result, rerender } = renderHook(
      ({ content, isStreaming }: { content: string; isStreaming: boolean }) =>
        useSmoothStreamText(content, isStreaming, { maxCharsPerFrame: 5, catchUpDivisor: 5 }),
      { initialProps: { content: "0123456789", isStreaming: true } },
    );
    rerender({ content: "012", isStreaming: true });
    expect(result.current).toBe("012");
  });

  it("snaps to the full text on the next update once streaming ends, with no trailing animation", () => {
    const { result, rerender } = renderHook(
      ({ content, isStreaming }: { content: string; isStreaming: boolean }) =>
        useSmoothStreamText(content, isStreaming, { maxCharsPerFrame: 2, minCharsPerFrame: 1, catchUpDivisor: 5 }),
      { initialProps: { content: "", isStreaming: true } },
    );
    rerender({ content: "final answer", isStreaming: true });
    flushFrame();
    expect(result.current.length).toBeLessThan("final answer".length);

    rerender({ content: "final answer", isStreaming: false });
    expect(result.current).toBe("final answer");
    // No pending frame should remain queued once streaming has finished.
    expect(frameQueue.length).toBe(0);
  });

  it("shows the full text immediately when disabled (reduced-motion)", () => {
    const { result, rerender } = renderHook(
      ({ content, isStreaming }: { content: string; isStreaming: boolean }) =>
        useSmoothStreamText(content, isStreaming, { enabled: false }),
      { initialProps: { content: "", isStreaming: true } },
    );
    rerender({ content: "reduced motion text", isStreaming: true });
    expect(result.current).toBe("reduced motion text");
    expect(frameQueue.length).toBe(0);
  });

  it("cancels the pending animation frame on unmount without throwing", () => {
    const { rerender, unmount } = renderHook(
      ({ content, isStreaming }: { content: string; isStreaming: boolean }) =>
        useSmoothStreamText(content, isStreaming, { maxCharsPerFrame: 1, minCharsPerFrame: 1, catchUpDivisor: 5 }),
      { initialProps: { content: "", isStreaming: true } },
    );
    rerender({ content: "some streamed text", isStreaming: true });
    expect(() => unmount()).not.toThrow();
  });
});
