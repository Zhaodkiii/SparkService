import { describe, expect, it } from "vitest";
import { shouldSubmitDoctorMessage } from "@/lib/hospital/composer-keyboard";
import { shouldSubmitOnEnter } from "@/lib/composer-keyboard";

describe("doctor composer keyboard", () => {
  it("sends only with Cmd/Ctrl + Enter", () => {
    expect(shouldSubmitDoctorMessage({ key: "Enter" })).toBe(false);
    expect(shouldSubmitDoctorMessage({ key: "Enter", shiftKey: true })).toBe(false);
    expect(shouldSubmitDoctorMessage({ key: "Enter", metaKey: true })).toBe(true);
    expect(shouldSubmitDoctorMessage({ key: "Enter", ctrlKey: true })).toBe(true);
  });

  it("does not submit during IME composition", () => {
    expect(shouldSubmitDoctorMessage({ key: "Enter", metaKey: true, keyCode: 229 })).toBe(false);
  });

  it("does not reuse the patient Enter-to-send rule", () => {
    expect(shouldSubmitOnEnter({ key: "Enter" })).toBe(true);
    expect(shouldSubmitDoctorMessage({ key: "Enter" })).toBe(false);
  });
});
