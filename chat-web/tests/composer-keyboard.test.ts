import { describe, expect, it } from "vitest";
import { isImeComposing, shouldSubmitOnEnter } from "@/lib/composer-keyboard";

describe("composer keyboard", () => {
  it("does not submit during IME composition", () => {
    expect(isImeComposing({ key: "Enter", keyCode: 229 })).toBe(true);
    expect(shouldSubmitOnEnter({ key: "Enter", keyCode: 229 })).toBe(false);
  });
  it("submits plain enter but preserves shift-enter", () => {
    expect(shouldSubmitOnEnter({ key: "Enter" })).toBe(true);
    expect(shouldSubmitOnEnter({ key: "Enter", shiftKey: true })).toBe(false);
  });
});
