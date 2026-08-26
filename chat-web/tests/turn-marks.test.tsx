import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { markForPhase, ReasoningMark, ToolMark, RespondingMark, RespondedMark } from "@/components/chat/turn/marks";
import type { TurnActivityPhase } from "@/types/chat";

describe("markForPhase", () => {
  it("maps each phase to the DeepTutor-aligned mark", () => {
    const cases: Array<[TurnActivityPhase, unknown]> = [
      ["exploring", ReasoningMark],
      ["waiting", ReasoningMark],
      ["using_tools", ToolMark],
      ["composing", RespondingMark],
      ["completed", RespondedMark],
      ["failed", RespondedMark],
      ["cancelled", RespondedMark],
      ["interrupted", RespondedMark],
    ];
    for (const [phase, expected] of cases) {
      expect(markForPhase(phase)).toBe(expected);
    }
  });

  it("every mark renders a valid, accessible (aria-hidden) svg", () => {
    for (const Mark of [ReasoningMark, ToolMark, RespondingMark, RespondedMark]) {
      const { container } = render(<Mark size={16} />);
      const svg = container.querySelector("svg");
      expect(svg).toBeTruthy();
      expect(svg).toHaveAttribute("aria-hidden", "true");
    }
  });
});
