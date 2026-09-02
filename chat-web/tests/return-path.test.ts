import { describe, expect, it } from "vitest";
import { loginUrl, safeReturnPath } from "@/lib/auth/return-path";

describe("safeReturnPath", () => {
  it("keeps doctor workspace paths", () => {
    expect(safeReturnPath("/doctor/conversations")).toBe("/doctor/conversations");
    expect(safeReturnPath("/doctor/conversations/abc")).toBe("/doctor/conversations/abc");
  });

  it("rejects open redirects and login loops", () => {
    expect(safeReturnPath("https://evil.example/x")).toBe("/chat");
    expect(safeReturnPath("//evil.example")).toBe("/chat");
    expect(safeReturnPath("/login")).toBe("/chat");
    expect(safeReturnPath(null)).toBe("/chat");
  });

  it("adds return_to only when leaving the default chat landing", () => {
    expect(loginUrl("/chat")).toBe("/login");
    expect(loginUrl("/doctor/conversations")).toBe("/login?return_to=%2Fdoctor%2Fconversations");
  });
});
