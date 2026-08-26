import { describe, expect, it } from "vitest";
import {
  blockAssociatedValue,
  decodeBlockPayload,
  normalizeBlockAnchor,
  normalizeSyncBlock,
  payloadKind,
} from "@/lib/chat/block-normalizer";

describe("decodeBlockPayload", () => {
  it("decodes a canonical tagged payload", () => {
    expect(decodeBlockPayload({ text: { _0: "hello" } })).toEqual({ kind: "text", value: "hello", status: "canonical" });
  });

  it("flags an unknown discriminator as unsupported", () => {
    const decoded = decodeBlockPayload({ foo: "bar" });
    expect(decoded.status).toBe("unsupported");
    expect(decoded.kind).toBe("");
  });

  it("flags a known discriminator missing the `_0` wrapper as contract_error", () => {
    const decoded = decodeBlockPayload({ text: "hello" });
    expect(decoded.kind).toBe("text");
    expect(decoded.status).toBe("contract_error");
  });

  it("flags multiple known discriminators as contract_error", () => {
    const decoded = decodeBlockPayload({ text: { _0: "a" }, html: { _0: "b" } });
    expect(decoded.status).toBe("contract_error");
  });
});

describe("payloadKind", () => {
  it("derives the kind solely from the discriminator", () => {
    expect(payloadKind({ search_summary: { _0: { summary: "x" } } })).toBe("searchSummary");
  });

  it("rejects a flat payload", () => {
    expect(payloadKind({ text: "hello" })).toBeNull();
    expect(payloadKind({ summary: "x" })).toBeNull();
  });
});

describe("blockAssociatedValue", () => {
  it("strips the `_0` wrapper using the block kind key", () => {
    expect(blockAssociatedValue({ kind: "text", payload: { text: { _0: "hi" } } })).toBe("hi");
    expect(blockAssociatedValue({ kind: "healthCards", payload: { health_cards: { _0: { cards: [] } } } })).toEqual({ cards: [] });
  });

  it("does not create a second flat payload model", () => {
    expect(blockAssociatedValue({ kind: "toolCall", payload: { tool_call_id: "k1" } })).toBeUndefined();
  });
});

describe("normalizeBlockAnchor", () => {
  it("accepts value-less anchors", () => {
    expect(normalizeBlockAnchor({ type: "messageStart" })).toEqual({ type: "messageStart" });
  });

  it("requires a value for beforeBlock/afterBlock/toolCall", () => {
    expect(normalizeBlockAnchor({ type: "toolCall", value: "k1" })).toEqual({ type: "toolCall", value: "k1" });
    expect(normalizeBlockAnchor({ type: "toolCall" })).toBeNull();
    expect(normalizeBlockAnchor({ type: "beforeBlock", value: "" })).toBeNull();
  });

  it("drops unknown anchor types", () => {
    expect(normalizeBlockAnchor({ type: "banana" })).toBeNull();
  });
});

describe("normalizeSyncBlock", () => {
  it("derives kind from the payload discriminator when `kind` is absent", () => {
    const block = normalizeSyncBlock({ id: "b1", node_role: "timeline", payload: { text: { _0: "你好" } }, revision: 2 });
    expect(block.kind).toBe("text");
    expect(block.payload).toEqual({ text: { _0: "你好" } });
    expect(block.node_role).toBe("timeline");
    expect(block.revision).toBe(2);
  });

  it("normalizes a strict union anchor", () => {
    const block = normalizeSyncBlock({ id: "b2", payload: { tool: { _0: { name: "search" } } }, anchor: { type: "toolCall", value: "k9" } });
    expect(block.kind).toBe("tool");
    expect(block.anchor).toEqual({ type: "toolCall", value: "k9" });
  });
});
