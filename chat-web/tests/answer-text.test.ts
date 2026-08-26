import { describe, expect, it } from "vitest";
import { extractAnswerText } from "@/lib/chat/answer-text";
import type { ChatBlockDTO } from "@/types/chat";

function block(overrides: Partial<ChatBlockDTO> & { id: string; kind: string }): ChatBlockDTO {
  return { status: "ready", revision: 1, order_key: 1, node_role: "timeline", payload: {}, ...overrides };
}

describe("extractAnswerText", () => {
  it("only concatenates content kinds, excluding tools and presentation cards", () => {
    const blocks = [
      block({ id: "a", kind: "text", payload: { text: { _0: "结论一" } } }),
      block({ id: "b", kind: "toolCall", tool_call_id: "k1" }),
      block({ id: "c", kind: "deepThought", payload: { deep_thought: { _0: { reasoning_content: "隐藏推理" } } } }),
      block({ id: "d", kind: "html", payload: { html: { _0: "结论二" } } }),
      block({ id: "e", kind: "healthCards" }),
      block({ id: "f", kind: "translatedText", payload: { translated_text: { _0: "结论三" } } }),
    ];
    expect(extractAnswerText(blocks)).toBe("结论一\n\n结论二\n\n结论三");
  });

  it("returns empty string for tool-only turns", () => {
    const blocks = [
      block({ id: "a", kind: "toolCall", tool_call_id: "k1" }),
      block({ id: "b", kind: "toolResult", tool_call_id: "k1" }),
    ];
    expect(extractAnswerText(blocks)).toBe("");
  });

  it("drops tool/toolPresentation text placeholders and empty text", () => {
    const blocks = [
      block({ id: "a", kind: "text", node_role: "timeline", payload: { text: { _0: "" } } }),
      block({ id: "b", kind: "text", node_role: "toolPresentation", payload: { text: { _0: "不应出现" } } }),
      block({ id: "c", kind: "text", node_role: "timeline", payload: { text: { _0: "正文" } } }),
    ];
    expect(extractAnswerText(blocks)).toBe("正文");
  });
});
