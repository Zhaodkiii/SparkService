import { describe, expect, it } from "vitest";
import { appleWebErrorForCode, appleWebUpstreamError } from "@/lib/auth/apple-web-errors";

describe("web apple error contract (CHAT-WEB-019 6.6)", () => {
  it("maps every ticket error code to user-facing copy", () => {
    for (const code of [
      "apple_web_callback_invalid",
      "apple_web_nonce_mismatch",
      "apple_web_token_invalid",
      "apple_web_transaction_replayed",
      "apple_web_identity_link_required",
      "apple_web_login_unavailable",
    ]) {
      expect(appleWebErrorForCode(code)).toBeTruthy();
    }
  });

  it("falls back to a generic retry message for unknown codes", () => {
    expect(appleWebErrorForCode("something_else")).toBe("登录未完成，请重试。");
  });

  it("distinguishes user cancellation from failures", () => {
    expect(appleWebErrorForCode("apple_web_user_cancelled")).toContain("已取消");
  });

  it("maps upstream business codes onto browser error codes", () => {
    expect(appleWebUpstreamError({ code: 40972 })).toBe("apple_web_identity_link_required");
    expect(appleWebUpstreamError({ code: 50371 })).toBe("apple_web_login_unavailable");
    expect(appleWebUpstreamError({ code: 99999 })).toBe("apple_web_token_invalid");
    expect(appleWebUpstreamError(null)).toBe("apple_web_token_invalid");
  });
});
